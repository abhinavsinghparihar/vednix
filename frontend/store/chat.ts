/**
 * Vednix chat store (Zustand) — single source of truth for the workspace.
 * Bridges REST (history/models) and the WS streaming protocol.
 */

"use client";

import { create } from "zustand";
import { api, WS_URL, type ConversationSummary, type UploadedFileMeta } from "@/lib/api";
import { getAccessToken } from "@/lib/tokenVault";
import { WSClient, type CoreStateName, type Language, type ServerFrame, type WSStatus } from "@/lib/ws";
import { tts } from "@/lib/tts";
import { detectSpeechLang, sanitizeForSpeech } from "@/lib/speechText";

export interface AttachmentChip {
  id: string;
  name: string;
  kind: string;
  size: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  plugins: string[];
  attachments?: AttachmentChip[];
  kbSources?: string[];
  /** Phase 5 web citations (live from the done frame, like kbSources). */
  sources?: { title: string; url: string }[];
  /** Phase 6 agent trace — accumulates via agent_step frames while streaming. */
  steps?: { step: string; detail: string }[];
  streaming: boolean;
  error: boolean;
}

/** Local voice arbitration: mic/speaking overrides the server-driven state so
 * LISTENING and SPEAKING orb animations (dead since the desktop app) finally fire. */
export type VoiceState = "idle" | "listening" | "speaking";

/** The OS surfaces: home hub, the chat stage, knowledge base, memory. */
export type WorkspaceView = "dash" | "chat" | "knowledge" | "memory";

export const MAX_CHARS = 32_000;

interface ChatStore {
  // data
  conversations: ConversationSummary[];
  activeId: string | null;
  messages: ChatMessage[];
  modelOptions: string[];
  activeModel: string | null; // null → conversation/backend default
  temperature: number;

  // live connection state
  wsStatus: WSStatus;
  coreState: CoreStateName;
  ollamaAvailable: boolean;
  generating: boolean;

  // internet research (Phase 5) & multi-agent loop (Phase 6)
  internet: boolean;
  setInternet: (v: boolean) => void;
  multiAgent: boolean;
  setMultiAgent: (v: boolean) => void;
  provider: string; // active provider label
  providerChoice: string | null;
  setProvider: (provider: string | null) => void;

  // voice (Phase 3)
  voiceState: VoiceState;
  voiceReplies: boolean;
  voiceRate: number;
  setVoiceState: (v: VoiceState) => void;
  setVoiceReplies: (on: boolean) => void;
  setVoiceRate: (rate: number) => void;
  speakMessage: (messageId: string) => void;
  stopSpeaking: () => void;

  // ui
  sidebarOpen: boolean;
  panelOpen: boolean;
  loadingConversations: boolean;
  loadingMessages: boolean;
  /** the OS view — Vednix is a workspace, not just a chatbox */
  view: WorkspaceView;
  setView: (v: WorkspaceView) => void;

  // attachments (Phase 4)
  draftAttachments: AttachmentChip[];
  uploadingCount: number;
  uploadDrafts: (files: FileList | File[]) => Promise<void>;
  removeDraftAttachment: (id: string) => void;

  // actions
  bootstrap: () => Promise<void>;
  selectConversation: (id: string | null) => Promise<void>;
  newChat: () => void;
  send: (text: string) => void;
  stop: () => void;
  removeConversation: (id: string) => Promise<void>;
  togglePin: (id: string) => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
  setLanguage: (lang: Language) => Promise<void>;
  setModel: (model: string | null) => void;
  setTemperature: (t: number) => void;

  toggleSidebar: () => void;
  togglePanel: () => void;
}

let ws: WSClient | null = null;
let wsToken: string | null = null;
let streamingId: string | null = null;
let ttsWired = false;

export const useChat = create<ChatStore>((set, get) => {
  if (!ttsWired && typeof window !== "undefined") {
    ttsWired = true;
    // TTS playback drives the orb's SPEAKING state (unless the mic owns it)
    tts.onSpeakingChange((speaking) => {
      const cur = get().voiceState;
      if (speaking) {
        if (cur !== "listening") set({ voiceState: "speaking" });
      } else if (cur === "speaking") {
        set({ voiceState: "idle" });
      }
    });
  }
  function handleFrame(frame: ServerFrame): void {
    const { messages, conversations } = get();
    switch (frame.type) {
      case "state_changed":
        set({ coreState: frame.state });
        break;

      case "conversation_created": {
        set({ activeId: frame.conversation_id });
        void refreshConversations(set);
        break;
      }

      case "message_started": {
        streamingId = frame.message_id;
        set({
          activeId: frame.conversation_id,
          messages: [
            ...messages,
            { id: frame.message_id, role: "assistant", content: "", plugins: [], streaming: true, error: false },
          ],
        });
        break;
      }

      case "token": {
        if (frame.message_id !== streamingId) break;
        set({
          messages: messages.map((m) =>
            m.id === frame.message_id ? { ...m, content: m.content + frame.content } : m,
          ),
        });
        break;
      }

      case "agent_step": {
        // Phase 6: stack the orchestration trace onto the streaming assistant bubble
        if (streamingId) {
          set({
            messages: messages.map((m) =>
              m.id === streamingId
                ? { ...m, steps: [...(m.steps ?? []), { step: frame.step, detail: frame.detail }] }
                : m,
            ),
          });
        }
        break;
      }

      case "message_done": {
        streamingId = null;
        set({
          generating: false,
          messages: messages.map((m) =>
            m.id === frame.message_id
              ? { ...m, streaming: false, plugins: frame.plugins, kbSources: frame.kb_sources ?? [],
                  sources: frame.sources ?? [], steps: frame.steps ?? m.steps }
              : m,
          ),
        });
        void refreshConversations(set);
        // Phase 3: auto-speak the finished reply when voice replies are on
        const done = messages.find((m) => m.id === frame.message_id);
        if (get().voiceReplies && done?.role === "assistant" && !frame.cancelled && done.content) {
          const conv = get().conversations.find((c) => c.id === frame.conversation_id);
          tts.speak(sanitizeForSpeech(done.content), detectSpeechLang(done.content, conv?.language ?? "auto"));
        }
        break;
      }

      case "title_updated":
        set({
          conversations: conversations.map((c) => (c.id === frame.conversation_id ? { ...c, title: frame.title } : c)),
        });
        break;

      case "error": {
        streamingId = null;
        const notice: ChatMessage = {
          id: `err-${Date.now()}`,
          role: "system",
          content: `⚠️ ${frame.message}`,
          plugins: [],
          streaming: false,
          error: true,
        };
        // replace a dangling streaming bubble if the error killed it
        const pruned = messages.filter((m) => !m.streaming);
        set({ generating: false, messages: [...pruned, notice] });
        break;
      }
    }
  }

  function ensureWs(): WSClient | null {
    if (typeof window === "undefined") return null;
    // A WebSocket upgrade cannot carry an Authorization header. The session
    // token is therefore part of the URL, and the socket must be rebuilt when
    // login/refresh changes it. Never retain an anonymous socket after auth.
    const token = getAccessToken();
    if (ws && wsToken !== token) {
      ws.close();
      ws = null;
      wsToken = null;
    }
    if (ws) return ws;
    const url = token ? `${WS_URL}?token=${encodeURIComponent(token)}` : WS_URL;
    wsToken = token;
    ws = new WSClient(url, handleFrame, (status) => set({ wsStatus: status }));
    ws.connect();
    return ws;
  }

  return {
    conversations: [],
    activeId: null,
    messages: [],
    modelOptions: [],
    activeModel: null,
    temperature: 0.7,

    wsStatus: "connecting",
    coreState: "IDLE",
    ollamaAvailable: true,
    generating: false,

    voiceState: "idle",
    voiceReplies: false,
    voiceRate: 1.0,

    internet: false,
    setInternet: (v) => set({ internet: v }),
    multiAgent: false,
    setMultiAgent: (v) => set({ multiAgent: v }),
    provider: "ollama",
    providerChoice: null,
    setProvider: (provider) => {
      set({ providerChoice: provider, modelOptions: [], activeModel: null });
      void api.models(provider).then((r) => set({ modelOptions: r.available.length ? r.available : [r.default], activeModel: r.default })).catch(() => undefined);
    },
    setVoiceState: (v) => set({ voiceState: v }),
    setVoiceReplies: (on) => {
      set({ voiceReplies: on });
      if (!on) tts.stop();
    },
    setVoiceRate: (rate) => {
      tts.rate = rate;
      set({ voiceRate: rate });
    },
    speakMessage: (messageId) => {
      const msg = get().messages.find((m) => m.id === messageId);
      if (!msg?.content) return;
      if (tts.speaking) {
        tts.stop();
        return;
      }
      const conv = get().conversations.find((c) => c.id === get().activeId);
      tts.speak(sanitizeForSpeech(msg.content), detectSpeechLang(msg.content, conv?.language ?? "auto"));
    },
    stopSpeaking: () => tts.stop(),

    sidebarOpen: true,
    panelOpen: true,
    view: "dash",
    setView: (v) => set({ view: v }),
    loadingConversations: true,
    loadingMessages: false,

    draftAttachments: [],
    uploadingCount: 0,

    uploadDrafts: async (incoming) => {
      const list = Array.from(incoming);
      if (!list.length) return;
      const room = 5 - get().draftAttachments.length;
      const batch = list.slice(0, Math.max(0, room));
      if (!batch.length) return;
      set({ uploadingCount: get().uploadingCount + batch.length });
      try {
        const uploaded = await api.uploadFiles(batch);
        const chips: AttachmentChip[] = uploaded.map((u: UploadedFileMeta) => ({
          id: u.id, name: u.name, kind: u.kind, size: u.size,
        }));
        set({ draftAttachments: [...get().draftAttachments, ...chips] });
      } catch (err) {
        const reason = err instanceof Error ? err.message : "Upload failed";
        set({
          messages: [
            ...get().messages,
            { id: `err-${Date.now()}`, role: "system", content: `⚠️ ${reason}`, plugins: [], streaming: false, error: true },
          ],
        });
      } finally {
        set({ uploadingCount: Math.max(0, get().uploadingCount - batch.length) });
      }
    },

    removeDraftAttachment: (id) =>
      set({ draftAttachments: get().draftAttachments.filter((a) => a.id !== id) }),

    bootstrap: async () => {
      // Do the HTTP/auth bootstrap first. Creating the socket before the
      // access token is available causes a legitimate 4401 handshake and an
      // unnecessary reconnect loop.
      try {
        const [health, models, conversations] = await Promise.all([
          api.health(),
          api.models(),
          api.listConversations(),
        ]);
        const options = models.available.length ? models.available : [models.default];
        set({
          conversations,
          modelOptions: options,
          activeModel: models.default,
          ollamaAvailable: health.ollama_available,
          provider: health.provider ?? "ollama",
          loadingConversations: false,
        });
        ensureWs();
      } catch {
        set({ loadingConversations: false, ollamaAvailable: false, wsStatus: "closed" });
      }
    },

    selectConversation: async (id) => {
      if (get().generating) get().stop();
      if (id === null) {
        set({ activeId: null, messages: [], view: "chat" });
        return;
      }
      set({ activeId: id, loadingMessages: true, messages: [], view: "chat" });
      try {
        const detail = await api.getConversation(id);
        set({
          messages: detail.messages.map((m) => ({
            id: m.id,
            role: m.role === "user" ? "user" : "assistant",
            content: m.content,
            plugins: m.plugins ? m.plugins.split(",") : [],
            attachments: (m.attachments as AttachmentChip[] | null) ?? undefined,
            streaming: false,
            error: false,
          })),
          loadingMessages: false,
        });
      } catch {
        set({ loadingMessages: false });
      }
    },

    newChat: () => {
      if (get().generating) get().stop();
      set({ activeId: null, messages: [], view: "chat" });
    },

    send: (raw) => {
      const text = raw.trim();
      const drafts = get().draftAttachments;
      if ((!text && drafts.length === 0) || get().generating || text.length > MAX_CHARS) return;
      if (get().uploadingCount > 0) return; // chips must settle before send
      const client = ensureWs();
      if (!client || !client.isOpen) {
        set({
          messages: [
            ...get().messages,
            { id: `u-${Date.now()}`, role: "user", content: text, plugins: [], streaming: false, error: false },
            {
              id: `err-${Date.now()}`,
              role: "system",
              content: "⚠️ Vednix backend is unreachable. Start it (`cd backend && python main.py`) — retrying in the background…",
              plugins: [],
              streaming: false,
              error: true,
            },
          ],
        });
        return;
      }
      const { activeId, activeModel, temperature, internet, multiAgent, conversations } = get();
      const conv = conversations.find((c) => c.id === activeId);
      const prompt =
        text ||
        (drafts.length
          ? "Analyze the attached file(s): summarize what's inside and answer inferred questions."
          : "");
      set({
        generating: true,
        draftAttachments: [],
        messages: [
          ...get().messages,
          {
            id: `u-${Date.now()}`, role: "user", content: prompt, plugins: [],
            attachments: drafts.length ? drafts : undefined, streaming: false, error: false,
          },
        ],
      });
      client.send({
        type: "user_message",
        content: prompt,
        conversation_id: activeId,
        model: activeModel ?? conv?.model ?? null,
        temperature,
        attachments: drafts.map((d) => d.id),
        internet,
        multi_agent: multiAgent,
      });
    },

    stop: () => {
      ws?.send({ type: "cancel" });
    },

    removeConversation: async (id) => {
      await api.deleteConversation(id);
      const { activeId, conversations } = get();
      set({ conversations: conversations.filter((c) => c.id !== id) });
      if (activeId === id) set({ activeId: null, messages: [] });
    },

    togglePin: async (id) => {
      const conv = get().conversations.find((c) => c.id === id);
      if (!conv) return;
      const updated = await api.patchConversation(id, { pinned: !conv.pinned });
      void refreshConversations(set, updated.id);
    },

    renameConversation: async (id, title) => {
      const clean = title.trim();
      if (!clean) return;
      const updated = await api.patchConversation(id, { title: clean });
      set({
        conversations: get().conversations.map((c) => (c.id === id ? { ...c, title: updated.title } : c)),
      });
    },

    setLanguage: async (lang) => {
      const { activeId } = get();
      set({
        conversations: get().conversations.map((c) => (c.id === activeId ? { ...c, language: lang } : c)),
      });
      if (activeId) {
        try {
          await api.patchConversation(activeId, { language: lang });
        } catch { /* non-fatal: server keeps old value */ }
      }
    },

    setModel: (model) => set({ activeModel: model }),
    setTemperature: (t) => set({ temperature: t }),

    toggleSidebar: () => set({ sidebarOpen: !get().sidebarOpen }),
    togglePanel: () => set({ panelOpen: !get().panelOpen }),
  };
});

async function refreshConversations(
  set: (partial: Partial<ChatStore>) => void,
  _preferId?: string,
): Promise<void> {
  try {
    const conversations = await api.listConversations();
    set({ conversations });
  } catch { /* transient */ }
}

/** The state the UI should actually render: voice arbitration beats server state
 * (listening/speaking are local hardware events the backend never sees). */
export function useDisplayCoreState(): CoreStateName {
  return useChat((s) =>
    s.voiceState === "listening" ? "LISTENING" : s.voiceState === "speaking" ? "SPEAKING" : s.coreState,
  );
}
