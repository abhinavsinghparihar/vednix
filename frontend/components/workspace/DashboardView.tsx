/**
 * Home hub — the "this is a system, not a chatbox" surface. Everything on
 * it is real: counts come from live APIs, recent chats from the store, the
 * ask-capsule routes into the chat stage with the question prefilled, and
 * the core card reflects the actual 8-state engine status.
 */

"use client";

import { useEffect, useState } from "react";
import { ArrowRight, ArrowUpRight, BookOpen, BrainCircuit, MessageSquare, MessageSquarePlus } from "lucide-react";
import { useChat, MAX_CHARS } from "@/store/chat";
import { api } from "@/lib/api";
import { Orb } from "@/components/orb/Orb";
import { Signature } from "@/components/brand/Signature";
import { timeAgo, cn } from "@/lib/utils";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Burning the midnight oil?";
  if (h < 12) return "Good morning.";
  if (h < 17) return "Good afternoon.";
  return "Good evening.";
}

function StatCard({ label, value, sub, icon: Icon, delay }: {
  label: string; value: string | number; sub: string; icon: typeof BookOpen; delay: number;
}) {
  return (
    <div
      className="glass group rounded-2xl p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-gold/25 hover:shadow-card"
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-gold/30 bg-gradient-to-br from-gold/25 to-ember/10">
        <Icon className="h-4 w-4 text-gold-bright" />
      </span>
      <p className="mt-4 font-display text-3xl font-bold tracking-tight text-cream">{value}</p>
      <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.24em] text-faint">{label}</p>
      <p className="mt-2 text-[11px] leading-snug text-muted">{sub}</p>
    </div>
  );
}

export function DashboardView() {
  const {
    conversations, selectConversation, newChat, setView,
    modelOptions, activeModel, ollamaAvailable, coreState,
  } = useChat();
  const [memoryCount, setMemoryCount] = useState<number | null>(null);
  const [docCount, setDocCount] = useState<number | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.listMemories().then((m) => setMemoryCount(m.length)).catch(() => setMemoryCount(0));
    api.listKnowledgeDocs().then((d) => setDocCount(d.length)).catch(() => setDocCount(0));
  }, []);

  const ask = (e: React.FormEvent) => {
    e.preventDefault();
    const text = q.trim();
    if (text) {
      try {
        sessionStorage.setItem("vednix.ask", text.slice(0, MAX_CHARS));
      } catch { /* composer simply opens empty */ }
    }
    setView("chat");
  };

  const recent = [...conversations]
    .sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || b.updated_at.localeCompare(a.updated_at))
    .slice(0, 4);
  const dateLine = new Date()
    .toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
    .toUpperCase();

  return (
    <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-6 py-10 md:px-10">
        {/* greeting */}
        <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-gold/65">{dateLine}</p>
        <h1 className="mt-3 font-display text-4xl font-extrabold tracking-tight text-cream md:text-5xl">
          नमस्ते. <span className="text-gold-gradient">{greeting()}</span>
        </h1>
        <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted">
          Vednix is{" "}
          <span className={cn("font-semibold", ollamaAvailable ? "text-gold-bright" : "text-danger")}>
            {ollamaAvailable ? "live and local" : "offline — backend not reachable"}
          </span>
          . Pick up where you left off, or start something new.
        </p>

        {/* ask capsule → chat with the question loaded */}
        <form
          onSubmit={ask}
          className="glass-liquid mt-8 flex w-full max-w-xl items-center gap-2 rounded-full py-1.5 pl-5 pr-1.5 transition-colors duration-300 focus-within:border-gold/40"
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
            aria-label="Ask in chat"
            className="group flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gold text-void transition-all duration-300 hover:bg-gold-bright hover:shadow-glow-gold"
          >
            <ArrowRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5" />
          </button>
        </form>

        {/* live stats — every number is real */}
        <div className="mt-9 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard icon={MessageSquare} label="conversations" value={conversations.length} sub="streaming · multilingual" delay={0} />
          <StatCard icon={BrainCircuit} label="memories" value={memoryCount ?? "…"} sub="long-term, on-device" delay={60} />
          <StatCard icon={BookOpen} label="knowledge docs" value={docCount ?? "…"} sub="FTS5 · cited answers" delay={120} />
          <StatCard icon={MessageSquarePlus} label="models" value={modelOptions.length || "…"} sub={`default · ${activeModel ?? "auto"}`} delay={180} />
        </div>

        <div className="mt-6 grid grid-cols-1 gap-3 lg:grid-cols-5">
          {/* recent conversations */}
          <div className="glass rounded-2xl p-5 lg:col-span-3">
            <div className="flex items-center justify-between">
              <p className="font-mono text-[10px] uppercase tracking-[0.26em] text-faint">Continue</p>
              <button
                onClick={() => newChat()}
                className="flex items-center gap-1.5 rounded-lg border border-gold/30 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-gold transition-colors duration-300 hover:bg-gold/10"
              >
                <MessageSquarePlus className="h-3 w-3" /> New chat
              </button>
            </div>
            <div className="mt-4 space-y-1.5">
              {recent.length === 0 ? (
                <p className="py-4 text-xs leading-relaxed text-faint">
                  No conversations yet — ask something above and Vednix starts your first one.
                </p>
              ) : (
                recent.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => void selectConversation(c.id)}
                    className="group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-300 hover:bg-gold/[0.07]"
                  >
                    <span className="min-w-0 flex-1 truncate text-sm text-cream/90">{c.title}</span>
                    <span className="shrink-0 font-mono text-[10px] text-faint">{timeAgo(c.updated_at)}</span>
                    <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-gold/0 transition-all duration-300 group-hover:text-gold" />
                  </button>
                ))
              )}
            </div>
          </div>

          {/* the core card */}
          <div className="gold-border flex flex-col items-center justify-center gap-3 rounded-2xl p-6 text-center lg:col-span-2">
            <Orb state={coreState} size={110} />
            <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-faint">
              core · <span className="text-gold-bright">{coreState}</span>
            </p>
            <Signature framed />
          </div>
        </div>
      </div>
    </div>
  );
}
