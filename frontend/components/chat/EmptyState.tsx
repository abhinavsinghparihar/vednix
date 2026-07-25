/**
 * Welcome screen — the first-impression moment. Hero orb, bilingual greeting,
 * suggestion chips that instantly demonstrate multilingual + plugins + memory.
 */

"use client";

import { motion } from "framer-motion";
import { Clock3, Cpu, Languages, BrainCircuit } from "lucide-react";
import { useChat, useDisplayCoreState } from "@/store/chat";
import { Orb } from "@/components/orb/Orb";
import { Signature } from "@/components/brand/Signature";

const SUGGESTIONS = [
  { icon: Clock3, label: "अभी समय क्या है?", hint: "plugin · Hindi" },
  { icon: Cpu, label: "What's my CPU usage right now?", hint: "plugin · instant" },
  { icon: Languages, label: "मुझे Hinglish में Python सिखाओ", hint: "multilingual LLM" },
  { icon: BrainCircuit, label: "Remember that I prefer concise answers", hint: "long-term memory" },
];

export function EmptyState() {
  const send = useChat((s) => s.send);
  const coreState = useDisplayCoreState();

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 pb-16">
      <motion.div
        initial={{ opacity: 0, scale: 0.85 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.7, ease: "easeOut" }}
        className="animate-float"
      >
        <Orb state={coreState} size={170} />
      </motion.div>

      <motion.h1
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15, duration: 0.5 }}
        className="text-gold-gradient mt-2 text-center text-3xl font-bold tracking-tight md:text-4xl"
      >
        नमस्ते. I'm Vednix.
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25, duration: 0.5 }}
        className="mt-3 max-w-md text-center text-sm leading-relaxed text-muted"
      >
        Your offline AI workspace — Hindi, Hinglish या English, किसी भी भाषा में बात कीजिए.
        <br />
        Everything runs on <span className="text-gold/90">your machine</span>. Nothing leaves it.
      </motion.p>

      <div className="mt-9 grid w-full max-w-xl grid-cols-1 gap-2.5 sm:grid-cols-2">
        {SUGGESTIONS.map((s, i) => (
          <motion.button
            key={s.label}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 + i * 0.07, duration: 0.4 }}
            onClick={() => send(s.label)}
            className="glass group flex items-center gap-3 rounded-2xl px-4 py-3.5 text-left transition-all duration-200 hover:border-[rgba(227,184,87,0.4)] hover:bg-[rgba(227,184,87,0.06)] hover:shadow-glow-gold"
          >
            <s.icon className="h-4.5 w-4.5 shrink-0 text-gold/80 transition-transform group-hover:scale-110 h-[18px] w-[18px]" />
            <span className="min-w-0">
              <span className="block truncate text-[13px] text-cream/90">{s.label}</span>
              <span className="text-[10px] uppercase tracking-widest text-faint">{s.hint}</span>
            </span>
          </motion.button>
        ))}
      </div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.9, duration: 0.7 }}
        className="mt-12"
      >
        <Signature framed />
      </motion.div>
    </div>
  );
}
