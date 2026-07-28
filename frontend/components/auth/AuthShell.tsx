/**
 * AuthShell — the cinematic frame every auth page lives inside (/login,
 * /signup). Left: the manifesto panel (wordmark, staggered verb lines, the
 * live Orb cycling its neural states, stats). Right: the glass card the page
 * fills. Neural background, mouse glow, theme toggle and the creator
 * signature stay exactly where the rest of the product keeps them.
 */

"use client";

import { useEffect, useState, type ReactNode } from "react";
import { motion } from "framer-motion";
import { Orb } from "@/components/orb/Orb";
import { Wordmark } from "@/components/brand/Wordmark";
import { Signature } from "@/components/brand/Signature";
import { ThemeToggle } from "@/components/brand/ThemeToggle";
import { NeuralBackground } from "@/components/background/NeuralBackground";
import { MouseGlow } from "@/components/background/MouseGlow";
import { EASE_CURVE } from "@/lib/utils";
import type { CoreStateName } from "@/lib/ws";

const VERBS = ["Create.", "Research.", "Code.", "Think."];
const ORB_CYCLE: CoreStateName[] = ["IDLE", "LISTENING", "THINKING", "SPEAKING"];

function Manifesto() {
  const [orbIdx, setOrbIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setOrbIdx((i) => (i + 1) % ORB_CYCLE.length), 1900);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="relative hidden flex-col justify-between p-12 lg:flex">
      <motion.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: EASE_CURVE }}
      >
        <Wordmark className="text-lg" />
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.3em] text-faint">
          The AI Operating System
        </p>
      </motion.div>

      <div className="flex flex-col items-start gap-8">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.9, delay: 0.15, ease: EASE_CURVE }}
        >
          <Orb state={ORB_CYCLE[orbIdx]} size={150} />
        </motion.div>
        <div>
          {VERBS.map((verb, i) => (
            <motion.p
              key={verb}
              className="font-display text-5xl font-extrabold leading-[1.12] tracking-tight text-cream"
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.7, delay: 0.25 + i * 0.12, ease: EASE_CURVE }}
            >
              {verb}
            </motion.p>
          ))}
          <motion.p
            className="mt-4 max-w-sm text-sm leading-relaxed text-muted"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.85 }}
          >
            Private-first. Multilingual. Yours entirely — every reply, every
            memory, every key stays on this machine.
          </motion.p>
        </div>
      </div>

      <motion.div
        className="flex items-center gap-8 font-mono text-[10px] uppercase tracking-[0.22em] text-faint"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 1 }}
      >
        <span>8 neural states</span>
        <span className="h-px w-6 bg-gold/30" />
        <span>0 telemetry</span>
        <span className="h-px w-6 bg-gold/30" />
        <span>हिंदी · Hinglish · English</span>
      </motion.div>
    </div>
  );
}

export function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <main className="relative flex min-h-dvh flex-col overflow-hidden bg-void text-cream">
      <NeuralBackground />
      <MouseGlow />

      <div className="absolute right-5 top-5 z-20">
        <ThemeToggle />
      </div>

      <div className="relative z-10 grid flex-1 lg:grid-cols-[1.05fr_1fr]">
        <Manifesto />

        <div className="flex items-center justify-center px-5 py-10 lg:px-12">
          <motion.div
            className="glass-strong w-full max-w-md rounded-3xl p-7 sm:p-9"
            initial={{ opacity: 0, y: 26, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.75, delay: 0.3, ease: EASE_CURVE }}
          >
            {/* mobile-only wordmark (manifesto hides below lg) */}
            <div className="mb-6 lg:hidden">
              <Wordmark className="text-base" />
            </div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-cream">
              {title}
            </h1>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">{subtitle}</p>
            <div className="mt-7">{children}</div>
          </motion.div>
        </div>
      </div>

      <footer className="relative z-10 pb-5 pt-2 text-center">
        <Signature />
      </footer>
    </main>
  );
}
