/**
 * Right control panel — every control is REAL:
 *   model selector   → /api/models, sent per message
 *   temperature      → WS payload (backend test-proven)
 *   language         → per-conversation, PATCHed server-side; drives the
 *                      multilingual system prompt (audit §8)
 *   internet + multi-agent → LangGraph research over SearXNG (Phase 5/6)
 * Memory & Knowledge graduated to full workspace views (see the Rail) —
 * each feature has exactly one home. About block carries identity + the
 * creator's signature.
 */

"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Globe, Volume2, ChevronDown, Play, Bot } from "lucide-react";
import { useChat } from "@/store/chat";
import { providerApi, type ProviderConfig } from "@/lib/authApi";
import type { Language } from "@/lib/ws";
import { tts } from "@/lib/tts";
import { Button, GlassPanel, Segmented, Slider, Switch } from "@/components/ui/primitives";

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
              "नमस्ते! मैं Vednix हूँ — I'm your personal AI workspace.",
              "hi-IN",
            )
          }
        >
          <Play className="h-3 w-3" /> Test voice
        </Button>
        <p className="text-[10.5px] leading-snug text-faint">
          Replies read aloud using your OS voices (on-device). Dictation: tap the mic
          — hi-IN handles हिंदी + Hinglish.
        </p>
      </GlassPanel>
    </Section>
  );
}

export function ControlPanel() {
  const { panelOpen, modelOptions, activeModel, setModel, temperature, setTemperature, providerChoice, setProvider, providerError } = useChat();
  const [providerOptions, setProviderOptions] = useState<ProviderConfig[]>([]);
  useEffect(() => {
    void providerApi.configured().then((r) => setProviderOptions(r.providers)).catch(() => setProviderOptions([]));
  }, []);
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
          className="glass-liquid z-20 m-3 ml-0 w-[292px] shrink-0 rounded-3xl px-5 py-5
                     max-lg:fixed max-lg:right-0 max-lg:top-0 max-lg:m-0 max-lg:h-full max-lg:rounded-l-3xl"
        >
          <div className="no-scrollbar flex h-full flex-col gap-6 overflow-y-auto">
            <p className="text-[10px] font-semibold uppercase tracking-[0.3em] text-faint">Studio</p>

            <Section title="Agent / Provider">
              <select
                value={providerChoice ?? "auto"}
                onChange={(e) => setProvider(e.target.value === "auto" ? null : e.target.value)}
                className="glass w-full rounded-xl px-3 py-2.5 text-sm text-cream outline-none [&>option]:bg-charcoal"
                aria-label="Select AI provider"
              >
                <option value="auto">Automatic priority (recommended)</option>
                <option value="ollama">Vednix Engine · Ollama</option>
                {providerOptions.filter((p) => p.provider !== "ollama" && p.enabled && p.has_key && p.verified && p.status === "connected").map((p) => (
                  <option key={p.provider} value={p.provider}>{p.label}</option>
                ))}
              </select>
              <p className="text-[11px] leading-snug text-faint">Choose a verified provider for this chat, or let Vednix fail over automatically.</p>
              {providerError && (
                <p role="status" className="rounded-lg border border-[#f0746e]/20 bg-[#f0746e]/[0.06] px-3 py-2 text-[11px] leading-snug text-[#f49a96]">
                  {providerError}
                </p>
              )}
            </Section>

            <Section title="Model">
              <div className="relative">
                <select
                  value={activeModel ?? ""}
                  onChange={(e) => setModel(e.target.value)}
                  className="glass w-full appearance-none rounded-xl px-3 py-2.5 text-sm text-cream outline-none focus:border-[rgba(227,184,87,0.4)] [&>option]:bg-charcoal"
                  aria-label="Select model"
                >
                  {modelOptions.length === 0 && (
                    <option value="">{providerError ? "No verified text model" : "Loading models…"}</option>
                  )}
                  {modelOptions.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
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

            {/* About block — product identity + creator signature */}
            <div className="glass mt-auto flex flex-col items-center gap-1.5 rounded-2xl px-4 py-4 text-center">
              <span className="font-display text-[11px] font-bold tracking-[0.3em] text-cream">
                VEDNIX AI
              </span>
              <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-faint">
                next-gen workspace · v0.1 · fully local
              </span>
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
