/**
 * Right control panel — every control is REAL:
 *   model selector   → /api/models, sent per message
 *   temperature      → WS payload (backend test-proven)
 *   language         → per-conversation, PATCHed server-side; drives the
 *                      multilingual system prompt (audit §8)
 *   memory viewer    → /api/memory CRUD
 * Internet / Vision / Sound toggles are disabled Phase badges — honest roadmap.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BrainCircuit, Globe, Volume2, Trash2, ChevronDown, Play, BookOpen, FileText, RefreshCw, Bot } from "lucide-react";
import { useChat } from "@/store/chat";
import { api, type KnowledgeDoc, type MemoryItem } from "@/lib/api";
import type { Language } from "@/lib/ws";
import { tts } from "@/lib/tts";
import { cn } from "@/lib/utils";
import { Badge, Button, GlassPanel, Segmented, Slider, Switch } from "@/components/ui/primitives";

const LANG_OPTIONS: { value: Language; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "hi", label: "हिंदी" },
  { value: "hinglish", label: "Hinglish" },
  { value: "en", label: "English" },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-faint">{title}</p>
      {children}
    </section>
  );
}

function MemorySection() {
  const [items, setItems] = useState<MemoryItem[] | null>(null);

  useEffect(() => {
    api.listMemories().then(setItems).catch(() => setItems([]));
  }, []);

  return (
    <Section title="Long-term memory">
      <GlassPanel className="max-h-44 space-y-2 overflow-y-auto p-3 no-scrollbar">
        {items === null ? (
          <div className="skeleton h-9 w-full" />
        ) : items.length === 0 ? (
          <p className="py-1 text-xs leading-relaxed text-faint">
            Nothing stored yet. In chat say{" "}
            <code className="text-gold/80">remember that …</code> and Vednix keeps it across sessions.
          </p>
        ) : (
          items.slice(0, 8).map((item) => (
            <div key={item.id} className="group flex items-start gap-2 text-xs">
              <BrainCircuit className="mt-0.5 h-3 w-3 shrink-0 text-gold/70" />
              <span className="min-w-0 flex-1 leading-snug text-cream/80">
                <span className="text-gold/60">#{item.id} {item.kind}</span> · {item.content}
              </span>
              <button
                aria-label={`Forget memory ${item.id}`}
                className="opacity-0 transition-opacity group-hover:opacity-100"
                onClick={() => {
                  void api.deleteMemory(item.id).then(() => setItems((cur) => cur?.filter((i) => i.id !== item.id) ?? []));
                }}
              >
                <Trash2 className="h-3 w-3 text-muted hover:text-danger" />
              </button>
            </div>
          ))
        )}
      </GlassPanel>
    </Section>
  );
}

function KnowledgeSection() {
  const [docs, setDocs] = useState<KnowledgeDoc[] | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () => api.listKnowledgeDocs().then(setDocs).catch(() => setDocs([]));
  useEffect(() => {
    refresh();
  }, []);

  const addFiles = async (files: FileList) => {
    setBusy(true);
    try {
      const uploaded = await api.uploadFiles(Array.from(files));
      for (const u of uploaded) {
        await api.addKnowledgeDoc({ uploaded_file_id: u.id, title: u.name });
      }
      await refresh();
    } catch { /* surfaced via console; panel stays usable */ } finally {
      setBusy(false);
    }
  };

  return (
    <Section title="Knowledge base">
      <input
        ref={fileRef}
        type="file"
        hidden
        multiple
        accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.pptx"
        onChange={(e) => {
          if (e.target.files?.length) void addFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <GlassPanel className="space-y-2 p-3">
        <p className="text-[11px] leading-snug text-faint">
          Documents here are searched automatically and cited into answers (FTS5, offline).
        </p>
        <Button variant="subtle" size="sm" className="w-full" disabled={busy} onClick={() => fileRef.current?.click()}>
          {busy ? <RefreshCw className="h-3 w-3 animate-spin" /> : <BookOpen className="h-3 w-3" />}
          Add document…
        </Button>
        {docs === null ? (
          <div className="skeleton h-8 w-full" />
        ) : docs.length === 0 ? (
          <p className="text-[11px] text-faint">Empty — index a handbook, notes, or a spec.</p>
        ) : (
          docs.slice(0, 6).map((d) => (
            <div key={d.id} className="group flex items-center gap-2 text-xs">
              <FileText className="h-3 w-3 shrink-0 text-gold/70" />
              <span className="min-w-0 flex-1 truncate text-cream/80">{d.title}</span>
              <span className="shrink-0 text-faint">{d.chunk_count} chunks</span>
              <button
                aria-label={`Remove ${d.title}`}
                className="opacity-0 transition-opacity group-hover:opacity-100"
                onClick={() => void api.deleteKnowledgeDoc(d.id).then(refresh)}
              >
                <Trash2 className="h-3 w-3 text-muted hover:text-danger" />
              </button>
            </div>
          ))
        )}
      </GlassPanel>
    </Section>
  );
}

function RoadmapSwitch({ icon: Icon, label, phase }: { icon: typeof Globe; label: string; phase: string }) {
  return (
    <div className="flex items-center justify-between rounded-xl px-1 py-1.5">
      <span className="flex items-center gap-2.5 text-sm text-muted">
        <Icon className="h-4 w-4" /> {label}
      </span>
      <span className="flex items-center gap-2">
        <Badge>{phase}</Badge>
        <Switch checked={false} disabled label={label} />
      </span>
    </div>
  );
}

function VoiceSection() {
  const { voiceReplies, setVoiceReplies, voiceRate, setVoiceRate } = useChat();
  // post-mount capability check (avoids hydration mismatch from speechSynthesis)
  const [ttsSupported, setTtsSupported] = useState(false);
  useEffect(() => setTtsSupported(tts.supported), []);

  return (
    <Section title="Voice">
      <GlassPanel className="space-y-3 p-3">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm text-cream/85">
            <Volume2 className="h-4 w-4 text-gold/80" /> Speak replies
          </span>
          <Switch
            checked={voiceReplies}
            onCheckedChange={setVoiceReplies}
            disabled={!ttsSupported}
            label="Speak replies"
          />
        </div>
        {!ttsSupported && (
          <p className="text-[11px] leading-snug text-faint">
            Speech synthesis isn't available in this browser.
          </p>
        )}
        <div className="space-y-1.5">
          <div className="flex justify-between text-[10px] text-faint">
            <span>Speed · {voiceRate.toFixed(1)}×</span>
            <span>Hindi voice auto-picked</span>
          </div>
          <Slider
            min={0.6}
            max={1.6}
            step={0.1}
            value={voiceRate}
            onChange={(e) => setVoiceRate(Number(e.target.value))}
            aria-label="Voice speed"
          />
        </div>
        <Button
          variant="subtle"
          size="sm"
          className="w-full"
          disabled={!ttsSupported}
          onClick={() =>
            tts.speak(
              "नमस्ते! मैं Vednix हूँ — I'm your offline AI workspace.",
              "hi-IN",
            )
          }
        >
          <Play className="h-3 w-3" /> Test voice
        </Button>
        <p className="text-[10.5px] leading-snug text-faint">
          Replies read aloud using your OS voices (offline). Dictation: tap the mic
          — hi-IN handles हिंदी + Hinglish.
        </p>
      </GlassPanel>
    </Section>
  );
}

export function ControlPanel() {
  const { panelOpen, modelOptions, activeModel, setModel, temperature, setTemperature } = useChat();
  const internet = useChat((s) => s.internet);
  const setInternet = useChat((s) => s.setInternet);
  const multiAgent = useChat((s) => s.multiAgent);
  const setMultiAgent = useChat((s) => s.setMultiAgent);
  const activeConv = useChat((s) => s.conversations.find((c) => c.id === s.activeId));
  const setLanguage = useChat((s) => s.setLanguage);

  return (
    <AnimatePresence>
      {panelOpen && (
        <motion.aside
          initial={{ x: 320, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 320, opacity: 0 }}
          transition={{ type: "spring", stiffness: 320, damping: 32 }}
          className="glass-strong z-20 h-full w-[292px] shrink-0 rounded-l-3xl border-r-0 px-5 py-5
                     max-lg:fixed max-lg:right-0 max-lg:top-0 max-lg:rounded-none"
        >
          <div className="no-scrollbar flex h-full flex-col gap-6 overflow-y-auto">
            <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-faint">Studio</p>

            <Section title="Model">
              <div className="relative">
                <select
                  value={activeModel ?? ""}
                  onChange={(e) => setModel(e.target.value)}
                  className="glass w-full appearance-none rounded-xl px-3 py-2.5 text-sm text-cream outline-none focus:border-[rgba(227,184,87,0.4)] [&>option]:bg-charcoal"
                  aria-label="Select model"
                >
                  {modelOptions.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                  {modelOptions.length === 0 && <option value="">qwen2.5:3b (offline)</option>}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
              </div>
            </Section>

            <Section title={`Temperature · ${temperature.toFixed(2)}`}>
              <Slider
                min={0}
                max={1.5}
                step={0.05}
                value={temperature}
                onChange={(e) => setTemperature(Number(e.target.value))}
                aria-label="Temperature"
              />
              <div className="flex justify-between text-[10px] text-faint">
                <span>precise</span><span>balanced</span><span>wild</span>
              </div>
            </Section>

            <Section title="Reply language">
              <Segmented
                options={LANG_OPTIONS}
                value={(activeConv?.language ?? "auto") as Language}
                onChange={(v) => void setLanguage(v)}
              />
              <p className="text-[11px] leading-snug text-faint">
                Auto mirrors your language. Others force every reply into that language/script.
              </p>
            </Section>

            <MemorySection />

            <KnowledgeSection />

            <VoiceSection />

            <Section title="Capabilities">
              <GlassPanel className="space-y-0.5 p-2">
                <div className="flex items-center justify-between rounded-xl px-1 py-1.5">
                  <span className="flex items-center gap-2.5 text-sm text-muted">
                    <Globe className="h-4 w-4" /> Internet search
                  </span>
                  <Switch checked={internet} onCheckedChange={setInternet} label="Internet search (SearXNG · cited answers)" />
                </div>
                <div className="flex items-center justify-between rounded-xl px-1 py-1.5">
                  <span className="flex items-center gap-2.5 text-sm text-muted">
                    <Bot className="h-4 w-4" /> Multi-agent mode
                  </span>
                  <Switch checked={multiAgent} onCheckedChange={setMultiAgent} label="Multi-agent deep research" />
                </div>
              </GlassPanel>
              <p className="text-[11px] leading-snug text-faint">
                Internet search runs a LangGraph agent over your SearXNG instance and cites sources — it needs
                connectivity + a reachable instance (self-hostable: docker run -p 8080:8080 searxng/searxng).
                Multi-agent adds a planner, researcher and critic that search, read and refine in loops — slower,
                deeper, and implies web research. Watch each agent step above the reply.
              </p>
            </Section>

            <p className="mt-auto text-center text-[10px] text-faint">
              Vednix AI · v0.1 · fully local
            </p>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
