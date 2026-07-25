/**
 * Enter — the final act. Big type, one honest three-command setup card with
 * a working copy button, and the primary launch CTA. The commands are the
 * real ones from the README — no fictional installers.
 */

"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowUpRight, Check, Copy } from "lucide-react";
import { MicroLabel, RevealInView } from "./shared";

const COMMANDS = [
  { cmd: "ollama pull qwen2.5:3b", note: "your local brain" },
  { cmd: "python backend/main.py", note: "FastAPI core · :8000" },
  { cmd: "npm --prefix frontend run dev", note: "Next.js shell · :3000" },
];

export function EnterSection() {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(COMMANDS.map((c) => c.cmd).join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked — the text is selectable anyway */
    }
  };

  return (
    <section id="enter" className="relative scroll-mt-24 border-t border-edge/50">
      <div className="mx-auto flex w-full max-w-5xl flex-col items-center px-6 py-24 text-center sm:px-10 lg:py-32">
        <RevealInView>
          <MicroLabel className="justify-center">03 · Enter</MicroLabel>
          <h2 className="mt-4 font-display text-5xl font-extrabold leading-[0.98] tracking-tight text-cream sm:text-6xl lg:text-7xl">
            Ready when
            <br />
            <span className="text-gold-gradient">you are.</span>
          </h2>
          <p className="mx-auto mt-6 max-w-md text-[15px] leading-relaxed text-muted">
            Three commands. One local model. A workspace that answers in your language — on the
            machine you already own.
          </p>
        </RevealInView>

        <RevealInView delay={0.15} className="mt-10 w-full max-w-xl">
          <div className="gold-border rounded-2xl p-1.5 text-left">
            <div className="flex items-center justify-between rounded-t-xl px-4 pb-2 pt-3">
              <span className="flex gap-1.5" aria-hidden>
                <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
                <span className="h-2.5 w-2.5 rounded-full bg-gold/40" />
              </span>
              <button
                onClick={copy}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted transition-colors duration-300 hover:border-gold/40 hover:text-gold-bright"
                aria-label="Copy setup commands"
              >
                {copied ? <Check className="h-3 w-3 text-gold-bright" /> : <Copy className="h-3 w-3" />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <div className="space-y-2 px-4 pb-4 pt-1 font-mono text-[13px] leading-relaxed">
              {COMMANDS.map((c) => (
                <p key={c.cmd} className="flex flex-wrap items-baseline gap-x-3">
                  <span className="select-none text-gold/50">$</span>
                  <span className="text-cream/90">{c.cmd}</span>
                  <span className="hidden text-faint sm:inline"># {c.note}</span>
                </p>
              ))}
            </div>
          </div>
        </RevealInView>

        <RevealInView delay={0.25}>
          <Link
            href="/chat"
            className="group mt-10 inline-flex h-13 items-center gap-3 rounded-xl bg-gold px-9 py-4 text-[12px] font-bold uppercase tracking-[0.16em] text-void transition-all duration-300 hover:bg-gold-bright hover:shadow-glow-gold"
          >
            Launch the workspace
            <ArrowUpRight className="h-4 w-4 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
          </Link>
        </RevealInView>
      </div>
    </section>
  );
}
