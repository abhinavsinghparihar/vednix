/**
 * The Living Core — the hero centerpiece. Instead of a stock background
 * video, the signature Vednix Orb performs live: it cycles through all 8
 * CoreStates (the same states the chat workspace streams over WebSocket),
 * wrapped in slow orbit rings, an aura, and floating glass badges that name
 * real, shipped features. No decoration here is a lie — every badge is a
 * capability that exists in the workspace behind "Launch App".
 */

"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Brain, Globe, Languages, Mic } from "lucide-react";
import { Orb } from "@/components/orb/Orb";
import type { CoreStateName } from "@/lib/ws";
import { cn } from "@/lib/utils";

const CYCLE: CoreStateName[] = [
  "IDLE",
  "LISTENING",
  "THINKING",
  "SEARCHING",
  "SPEAKING",
  "EXECUTING",
  "LEARNING",
  "UPDATING",
];

const STATE_BLURB: Record<CoreStateName, string> = {
  IDLE: "at rest",
  LISTENING: "hearing you",
  THINKING: "reasoning",
  SEARCHING: "scanning the web",
  SPEAKING: "answering",
  EXECUTING: "running plugins",
  LEARNING: "saving memory",
  UPDATING: "refreshing",
};

interface Badge {
  icon: typeof Globe;
  title: string;
  sub: string;
  pos: string; // absolute anchor on desktop
  dur: number; // breathing loop seconds
  dx: number;
  dy: number;
}

const BADGES: Badge[] = [
  {
    icon: Globe,
    title: "Deep research",
    sub: "multi-agent · cited",
    pos: "lg:-top-3 lg:-right-1",
    dur: 5.0,
    dx: 3,
    dy: -10,
  },
  {
    icon: Mic,
    title: "Voice-native",
    sub: "speak & listen",
    pos: "lg:top-[38%] lg:-left-12",
    dur: 5.6,
    dx: -3,
    dy: 9,
  },
  {
    icon: Brain,
    title: "Long-term memory",
    sub: "it remembers",
    pos: "lg:bottom-[4%] lg:-right-8",
    dur: 4.8,
    dx: -2,
    dy: -11,
  },
  {
    icon: Languages,
    title: "हिंदी · Hinglish",
    sub: "your language",
    pos: "lg:bottom-[3%] lg:-left-3",
    dur: 5.3,
    dx: 2,
    dy: 10,
  },
];

export function OrbStage() {
  const [idx, setIdx] = useState(0);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (reduce) return;
    const t = setInterval(() => setIdx((i) => (i + 1) % CYCLE.length), 1900);
    return () => clearInterval(t);
  }, [reduce]);

  const state = CYCLE[idx];

  return (
    <div className="relative flex flex-col items-center">
      {/* stage */}
      <div className="relative flex items-center justify-center">
        {/* aura */}
        <div
          aria-hidden
          className="absolute h-[420px] w-[420px] rounded-full bg-[radial-gradient(circle,rgba(227,184,87,0.14),transparent_62%)] blur-2xl"
        />
        <div className="scale-[0.74] transition-transform duration-700 sm:scale-90 lg:scale-100">
          <div className="relative flex h-[380px] w-[380px] items-center justify-center">
            {/* orbit rings */}
            <div
              aria-hidden
              className="absolute inset-0 animate-orbit rounded-full border border-gold/15"
            >
              <span className="absolute -top-[3px] left-1/2 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-gold-bright shadow-glow-gold" />
            </div>
            <div
              aria-hidden
              className="absolute inset-[42px] animate-orbit-rev rounded-full border border-dashed border-gold/12"
            >
              <span className="absolute left-1/2 top-full h-1 w-1 -translate-x-1/2 rounded-full bg-ember/80" />
            </div>

            <Orb state={state} size={250} />

            {/* floating glass badges — desktop anchors */}
            {BADGES.map((b, i) => (
              <motion.div
                key={b.title}
                initial={{ opacity: 0, scale: 0.6 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ type: "spring", stiffness: 120, damping: 16, delay: 0.5 + i * 0.14 }}
                className={cn("absolute z-10 hidden lg:block", b.pos)}
              >
                <motion.div
                  animate={reduce ? {} : { y: [0, b.dy, 0], x: [0, b.dx, 0] }}
                  transition={{ duration: b.dur, repeat: Infinity, ease: "easeInOut" }}
                  whileHover={{ scale: 1.06, rotate: i % 2 === 0 ? 1.2 : -1.2 }}
                  className="glass flex cursor-default items-center gap-3 rounded-2xl px-4 py-2.5 shadow-card"
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-gold/30 bg-gradient-to-br from-gold/30 to-ember/15 shadow-glow-gold">
                    <b.icon className="h-4 w-4 text-gold-bright" />
                  </span>
                  <span className="leading-tight">
                    <span className="block text-[13px] font-semibold tracking-tight text-cream">
                      {b.title}
                    </span>
                    <span className="mt-0.5 block text-[10px] font-medium uppercase tracking-[0.12em] text-faint">
                      {b.sub}
                    </span>
                  </span>
                </motion.div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>

      {/* live state readout */}
      <div className="mt-5 flex items-center gap-2.5 font-mono text-[10px] uppercase tracking-[0.3em] text-faint">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-gold/60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-gold" />
        </span>
        <span>
          core · <span className="text-gold-bright">{state}</span>
          <span className="ml-2 normal-case tracking-normal text-faint/80">
            {STATE_BLURB[state]}
          </span>
        </span>
      </div>

      {/* badges — compact grid on small screens */}
      <div className="mt-6 grid w-full max-w-sm grid-cols-2 gap-3 lg:hidden">
        {BADGES.map((b) => (
          <div key={b.title} className="glass flex items-center gap-2.5 rounded-2xl px-3.5 py-2.5">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-gold/30 bg-gradient-to-br from-gold/30 to-ember/15">
              <b.icon className="h-3.5 w-3.5 text-gold-bright" />
            </span>
            <span className="leading-tight">
              <span className="block text-[12px] font-semibold tracking-tight text-cream">
                {b.title}
              </span>
              <span className="block text-[9px] font-medium uppercase tracking-[0.12em] text-faint">
                {b.sub}
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
