/**
 * Capabilities — the honest grid. Six shipped systems, each described in one
 * true sentence with its real engine name as the tag. No roadmap fiction,
 * no marketing abstractions: everything here works in the workspace today.
 */

"use client";

import { Brain, Cpu, FileSearch, FolderSearch, Mic, Workflow } from "lucide-react";
import { MicroLabel, RevealInView } from "./shared";

const ITEMS = [
  {
    icon: Cpu,
    title: "Local-first intelligence",
    body: "Streams tokens from the Vednix Engine on your own machine. Model, temperature and language, dialled in live — Hindi, Hinglish or English.",
    tag: "engine.stream_reply",
  },
  {
    icon: Workflow,
    title: "Deep research agents",
    body: "Planner, searcher, critic — a LangGraph crew that decomposes your question and shows every step as it works.",
    tag: "agents.research",
  },
  {
    icon: Mic,
    title: "Voice, natively",
    body: "Speak in Hindi, Hinglish or English; hear answers read back in chunks as they stream. The hi-IN recognizer does the juggling.",
    tag: "speech · hi-IN",
  },
  {
    icon: Brain,
    title: "Memory that endures",
    body: "Conversations, facts and preferences persist in SQLite — searchable, deletable, and never sent anywhere.",
    tag: "memory.sqlite",
  },
  {
    icon: FolderSearch,
    title: "Knowledge base",
    body: "Index your own documents and query them with FTS5 + BM25. Answers arrive with pinpoint «snippets» of the source.",
    tag: "knowledge.fts5",
  },
  {
    icon: FileSearch,
    title: "Files & vision",
    body: "Drop PDFs, sheets, decks, CSVs or images straight into chat. Extraction and understanding are built into the pipeline.",
    tag: "files.extract",
  },
];

export function Capabilities() {
  return (
    <section id="capabilities" className="relative scroll-mt-24 border-t border-edge/50">
      <div className="mx-auto w-full max-w-7xl px-6 py-24 sm:px-10 lg:px-14 lg:py-32">
        <RevealInView>
          <MicroLabel>02 · Capabilities</MicroLabel>
          <h2 className="mt-4 max-w-3xl font-display text-4xl font-extrabold leading-[1.02] tracking-tight text-cream sm:text-5xl lg:text-6xl">
            Every capability,
            <br />
            <span className="text-gold-gradient">engineered in.</span>
          </h2>
        </RevealInView>

        <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {ITEMS.map((it, i) => (
            <RevealInView key={it.title} delay={0.08 * (i % 3)}>
              <article className="group glass h-full rounded-2xl p-6 transition-all duration-300 hover:-translate-y-1 hover:border-gold/25 hover:shadow-card">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-gold/30 bg-gradient-to-br from-gold/25 to-ember/10 transition-shadow duration-300 group-hover:shadow-glow-gold">
                  <it.icon className="h-5 w-5 text-gold-bright" />
                </span>
                <h3 className="mt-5 font-display text-lg font-bold tracking-tight text-cream">
                  {it.title}
                </h3>
                <p className="mt-2.5 text-sm leading-relaxed text-muted">{it.body}</p>
                <p className="mt-5 font-mono text-[10px] tracking-[0.14em] text-faint group-hover:text-gold/70 transition-colors duration-300">
                  {it.tag}
                </p>
              </article>
            </RevealInView>
          ))}
        </div>
      </div>
    </section>
  );
}
