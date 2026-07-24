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

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BrainCircuit, Globe, ImageIcon, Volume2, Trash2, ChevronDown } from "lucide-react";
import { useChat } from "@/store/chat";
import { api, type MemoryItem } from "@/lib/api";
import type { Language } from "@/lib/ws";
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

export function ControlPanel() {
  const { panelOpen, modelOptions, activeModel, setModel, temperature, setTemperature } = useChat();
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

            <Section title="Capabilities">
              <GlassPanel className="space-y-0.5 p-2">
                <RoadmapSwitch icon={Globe} label="Internet search" phase="Phase 5" />
                <RoadmapSwitch icon={ImageIcon} label="Vision · OCR" phase="Phase 4" />
                <RoadmapSwitch icon={Volume2} label="Voice" phase="Phase 3" />
              </GlassPanel>
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
