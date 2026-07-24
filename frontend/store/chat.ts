/**
 * Vednix chat store (Zustand) — single source of truth for the workspace.
 * Bridges REST (history/models) and the WS streaming protocol.
 */

"use client";

import { create } from "zustand";
import { api, WS_URL, type ConversationSummary } from "@/lib/api";
import { WSClient, type CoreStateName, type Language, type ServerFrame, type WSStatus } from "@/lib/ws";
import { tts } from "@/lib/tts";
import { detectSpeechLang, sanitizeForSpeech } from "@/lib/speechText";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  plugins: string[];
  streaming: boolean;
  error: boolean;
}

/** Local voice arbitration: mic/speaking overrides the server-driven state so
 * LISTENING and SPEAKING orb animations (dead since the desktop app) finally fire. */
export type VoiceState = "idle" | "listening" | "speaking";

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
    const { messages, activeId, conversations } = get();
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

      case "message_done": {
        streamingId = null;
        set({
          generating: false,
          messages: messages.map((m) =>
            m.id === frame.message_id ? { ...m, streaming: false, plugins: frame.plugins } : m,
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
    if (ws) return ws;
    if (typeof window === "undefined") return null;
    ws = new WSClient(WS_URL, handleFrame, (status) => set({ wsStatus: status }));
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
    loadingConversations: true,
    loadingMessages: false,

    bootstrap: async () => {
      ensureWs();
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
          loadingConversations: false,
        });
      } catch {
        set({ loadingConversations: false, ollamaAvailable: false });
      }
    },

    selectConversation: async (id) => {
      if (get().generating) get().stop();
      if (id === null) {
        set({ activeId: null, messages: [] });
        return;
      }
      set({ activeId: id, loadingMessages: true, messages: [] });
      try {
        const detail = await api.getConversation(id);
        set({
          messages: detail.messages.map((m) => ({
            id: m.id,
            role: m.role === "user" ? "user" : "assistant",
            content: m.content,
            plugins: m.plugins ? m.plugins.split(",") : [],
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
      set({ activeId: null, messages: [] });
    },

    send: (raw) => {
      const text = raw.trim();
      if (!text || get().generating || text.length > MAX_CHARS) return;
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
      const { activeId, activeModel, temperature, conversations } = get();
      const conv = conversations.find((c) => c.id === activeId);
      set({
        generating: true,
        messages: [
          ...get().messages,
          { id: `u-${Date.now()}`, role: "user", content: text, plugins: [], streaming: false, error: false },
        ],
      });
      client.send({
        type: "user_message",
        content: text,
        conversation_id: activeId,
        model: activeModel ?? conv?.model ?? null,
        temperature,
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
