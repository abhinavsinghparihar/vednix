/**
 * Hero — full-viewport cinematic opening. Left: the manifesto (staggered
 * entrance), a functional "ask anything" capsule that routes straight into
 * the workspace with the question prefilled, CTAs and honest product stats.
 * Right: the Living Core (OrbStage). Edge details: numbered section
 * indicators and an animated scroll cue.
 */

"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowRight, ArrowUpRight } from "lucide-react";
import { MicroLabel, Reveal } from "./shared";
import { OrbStage } from "./OrbStage";
import { Signature } from "@/components/brand/Signature";
import { MAX_CHARS, useChat } from "@/store/chat";

const STATS = [
  { value: "109", label: "automated tests, green" },
  { value: "8", label: "neural core states" },
  { value: "0", label: "telemetry, ever" },
];

const INDICATORS = [
  { n: "01", label: "Core", href: "#top" },
  { n: "02", label: "Capabilities", href: "#capabilities" },
  { n: "03", label: "Enter", href: "#enter" },
];

function AskCapsule() {
  const [q, setQ] = useState("");
  const router = useRouter();

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = q.trim();
    if (text) {
      try {
        sessionStorage.setItem("vednix.ask", text.slice(0, MAX_CHARS));
      } catch {
        /* private mode — the workspace simply opens empty */
      }
      // The capsule's intent is "open the stage with this question" — the
      // store survives client-side routing, so aim the shell at chat now
      // (hard arrivals are covered by the /chat mount guard).
      useChat.getState().setView("chat");
    }
    router.push("/chat");
  };

  return (
    <form
      onSubmit={submit}
      className="glass flex w-full max-w-lg items-center gap-2 rounded-full py-1.5 pl-5 pr-1.5 transition-colors duration-300 focus-within:border-gold/35"
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        maxLength={MAX_CHARS}
        placeholder="Ask anything… हिंदी में भी"
        aria-label="Ask Vednix anything"
        className="min-w-0 flex-1 bg-transparent text-sm text-cream placeholder:text-faint focus:outline-none"
      />
      <button
        type="submit"
        aria-label="Ask in the workspace"
        className="group flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gold text-void transition-all duration-300 hover:bg-gold-bright hover:shadow-glow-gold"
      >
        <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5" />
      </button>
    </form>
  );
}

export function Hero() {
  return (
    <section id="top" className="relative flex flex-col lg:min-h-dvh">
      <div className="mx-auto grid w-full max-w-7xl flex-1 grid-cols-1 items-center gap-12 px-6 pb-20 pt-32 sm:px-10 lg:grid-cols-12 lg:gap-6 lg:px-14 lg:pb-16 lg:pt-24">
        {/* manifesto */}
        <div className="lg:col-span-6">
          <Reveal>
            <span className="glass inline-flex items-center gap-2.5 rounded-full px-4 py-1.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute h-full w-full animate-ping rounded-full bg-gold/60" />
                <span className="relative h-1.5 w-1.5 rounded-full bg-gold" />
              </span>
              <MicroLabel>Your personal AI workspace</MicroLabel>
            </span>
          </Reveal>

          <Reveal delay={0.12}>
            <h1 className="mt-7 font-display text-[clamp(2.9rem,7.2vw,6.2rem)] font-extrabold uppercase leading-[0.94] tracking-[-0.02em] text-cream">
              Your machine.
              <br />
              <span className="inline-flex items-center gap-[0.14em]">
                Your
                <span
                  aria-hidden
                  className="inline-flex h-[0.6em] w-[1.06em] items-center justify-center rounded-full border-2 border-gold/55 bg-gold/10"
                >
                  <span className="text-[0.24em] font-bold not-italic text-gold-bright">अ</span>
                </span>
              </span>{" "}
              <span className="text-gold-gradient">language.</span>
              <br />
              Your intelligence.
            </h1>
          </Reveal>

          <Reveal delay={0.24}>
            <p className="mt-7 max-w-md text-[15px] leading-relaxed text-muted">
              Vednix AI is a cinematic chat and research workspace that runs entirely on your
              hardware — streaming answers, deep research agents, voice and memory, in Hindi,
              Hinglish, English and beyond. No cloud required. Nothing leaves the room.
            </p>
          </Reveal>

          <Reveal delay={0.36} className="mt-8">
            <AskCapsule />
          </Reveal>

          <Reveal delay={0.46}>
            <div className="mt-6 flex flex-wrap items-center gap-4">
              <Link
                href="/chat"
                className="group flex h-12 items-center gap-2.5 rounded-xl bg-gold px-7 text-[11px] font-bold uppercase tracking-[0.14em] text-void transition-all duration-300 hover:bg-gold-bright hover:shadow-glow-gold"
              >
                Enter the workspace
                <ArrowUpRight className="h-4 w-4 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
              </Link>
              <Link
                href="#capabilities"
                className="group flex h-12 items-center gap-2.5 rounded-xl border border-white/20 px-7 text-[11px] font-bold uppercase tracking-[0.14em] text-cream/85 transition-colors duration-300 hover:border-gold/50 hover:text-cream"
              >
                Explore capabilities
                <ArrowDown className="h-4 w-4 text-gold/80 transition-transform duration-300 group-hover:translate-y-0.5" />
              </Link>
            </div>
          </Reveal>

          <Reveal delay={0.56}>
            <dl className="mt-10 flex flex-wrap gap-x-12 gap-y-6 border-t border-white/5 pt-7">
              {STATS.map((s) => (
                <div key={s.label}>
                  <dt className="sr-only">{s.label}</dt>
                  <dd className="font-display text-3xl font-bold tracking-tight text-gold-gradient">
                    {s.value}
                  </dd>
                  <dd className="mt-1 font-mono text-[9px] uppercase tracking-[0.24em] text-faint">
                    {s.label}
                  </dd>
                </div>
              ))}
            </dl>
          </Reveal>
        </div>

        {/* the living core */}
        <div className="lg:col-span-6 lg:pl-6">
          <Reveal delay={0.3}>
            <OrbStage />
          </Reveal>
        </div>
      </div>

      {/* numbered section indicators */}
      <nav
        aria-label="Sections"
        className="absolute right-7 top-1/2 hidden -translate-y-1/2 flex-col gap-7 xl:flex"
      >
        {INDICATORS.map((it, i) => (
          <Link
            key={it.n}
            href={it.href}
            className="group flex items-center gap-3 font-mono text-[10px] font-bold tracking-[0.24em] uppercase"
          >
            <span
              className={
                i === 0 ? "w-4 text-gold" : "w-4 text-faint transition-colors group-hover:text-gold"
              }
            >
              {it.n}
            </span>
            <span
              className={
                i === 0
                  ? "text-cream"
                  : "text-faint transition-colors duration-300 group-hover:text-cream"
              }
            >
              {it.label}
            </span>
          </Link>
        ))}
      </nav>

      {/* scroll cue */}
      <div
        aria-hidden
        className="pointer-events-none absolute bottom-7 left-1/2 hidden -translate-x-1/2 flex-col items-center gap-2.5 lg:flex"
      >
        <span className="font-mono text-[9px] tracking-[0.42em] text-faint">SCROLL</span>
        <span className="h-8 w-px animate-scroll-cue bg-gradient-to-b from-gold/80 to-transparent" />
      </div>

      {/* architectural edge anchors */}
      <p className="pointer-events-none absolute bottom-7 left-6 hidden font-mono text-[9px] tracking-[0.3em] text-faint lg:block xl:left-14">
        VEDNIX AI · 2026
      </p>
      <Signature className="pointer-events-none absolute bottom-7 right-6 hidden lg:inline-flex xl:right-14" />
    </section>
  );
}
