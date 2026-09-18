/**
 * Onboarding shared atoms — the wizard shell (progress rail + animated step
 * transitions), copy-to-clipboard chips, status dots, spec chips and the
 * polling hook the auto-detector uses. Everything inherits the Obsidian/Ivory
 * glass system; nothing here invents a new visual language.
 */

"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Copy } from "lucide-react";
import { Wordmark } from "@/components/brand/Wordmark";
import { ThemeToggle } from "@/components/brand/ThemeToggle";
import { NeuralBackground } from "@/components/background/NeuralBackground";
import { MouseGlow } from "@/components/background/MouseGlow";
import { cn, EASE_CURVE } from "@/lib/utils";

/* --- shell ------------------------------------------------------------------ */

export function WizardShell({
  step,
  total,
  stepLabel,
  children,
}: {
  step: number;
  total: number;
  stepLabel: string;
  children: ReactNode;
}) {
  return (
    <main className="relative flex min-h-dvh flex-col overflow-hidden bg-void text-cream">
      <NeuralBackground />
      <MouseGlow />

      <header className="relative z-10 flex items-center justify-between px-6 pt-5 sm:px-10">
        <Wordmark className="text-sm" />
        <div className="flex items-center gap-4">
          <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-faint">
            {stepLabel} · {Math.min(step + 1, total)}/{total}
          </span>
          <ThemeToggle />
        </div>
      </header>

      {/* gold progress hairline */}
      <div className="relative z-10 mx-6 mt-4 h-px bg-white/[0.06] sm:mx-10">
        <motion.div
          className="h-px bg-gradient-to-r from-gold/40 via-gold to-gold-bright shadow-[0_0_8px_rgba(227,184,87,0.5)]"
          animate={{ width: `${(Math.min(step + 1, total) / total) * 100}%` }}
          transition={{ duration: 0.6, ease: EASE_CURVE }}
        />
      </div>

      <div className="relative z-10 flex flex-1 items-start justify-center overflow-y-auto px-5 pb-16 pt-8 sm:pt-12">
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            className="w-full max-w-3xl"
            initial={{ opacity: 0, y: 22, scale: 0.99 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -14, scale: 0.995 }}
            transition={{ duration: 0.45, ease: EASE_CURVE }}
          >
            {children}
          </motion.div>
        </AnimatePresence>
      </div>

      <footer className="relative z-10 pb-5 text-center">
      </footer>
    </main>
  );
}

/* --- typography -------------------------------------------------------------- */

export function StepTitle({ kicker, title, sub }: { kicker: string; title: string; sub?: string }) {
  return (
    <div className="mb-8 text-center">
      <motion.p
        className="mb-2 font-mono text-[10px] uppercase tracking-[0.3em] text-gold"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}
      >
        {kicker}
      </motion.p>
      <motion.h1
        className="font-display text-4xl font-extrabold tracking-tight text-cream sm:text-5xl"
        initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15, duration: 0.6, ease: EASE_CURVE }}
      >
        {title}
      </motion.h1>
      {sub && (
        <motion.p
          className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-muted"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
        >
          {sub}
        </motion.p>
      )}
    </div>
  );
}

/* --- chips & status ------------------------------------------------------------- */

export function CopyChip({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        void navigator.clipboard?.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      aria-label={`Copy ${text}`}
      className={cn(
        "glass group flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left",
        "transition-colors duration-200 hover:border-gold/35",
      )}
    >
      <code className="min-w-0 flex-1 truncate font-mono text-[13px] text-gold-bright">{text}</code>
      {label && <span className="hidden text-[11px] text-faint sm:block">{label}</span>}
      {copied ? <Check className="h-4 w-4 shrink-0 text-emerald-400" /> : <Copy className="h-4 w-4 shrink-0 text-faint group-hover:text-gold-bright" />}
    </button>
  );
}

export function StatusDot({ tone, pulse }: { tone: "ok" | "warn" | "fail" | "idle"; pulse?: boolean }) {
  const colors = {
    ok: "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.55)]",
    warn: "bg-gold shadow-[0_0_10px_rgba(227,184,87,0.55)]",
    fail: "bg-[#f0746e] shadow-[0_0_10px_rgba(240,116,110,0.5)]",
    idle: "bg-white/20",
  } as const;
  return (
    <span className="relative inline-flex h-2.5 w-2.5">
      <span className={cn("inline-flex h-2.5 w-2.5 rounded-full", colors[tone])} />
      {pulse && <span className={cn("absolute inset-0 animate-ping rounded-full opacity-60", colors[tone])} />}
    </span>
  );
}

export function SpecChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="glass inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5">
      <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-faint">{label}</span>
      <span className="text-[11px] font-semibold text-cream">{value}</span>
    </span>
  );
}

/* --- polling (ollama auto-detect) ----------------------------------------------- */

export function usePoller(fn: () => Promise<void>, ms: number, active = true) {
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    if (!active) return;
    let dead = false;
    const tick = async () => {
      if (!dead) await saved.current();
    };
    void tick();
    const t = setInterval(() => void tick(), ms);
    return () => {
      dead = true;
      clearInterval(t);
    };
  }, [ms, active]);
}
