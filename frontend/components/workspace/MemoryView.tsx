/**
 * Memory view — everything Vednix has chosen to remember, in one honest
 * list. Add facts directly or prune them; in chat you can also just say
 * "remember that …". Data: real /api/memory CRUD.
 */

"use client";

import { useEffect, useState } from "react";
import { BrainCircuit, Loader2, Plus, Trash2 } from "lucide-react";
import { api, type MemoryItem } from "@/lib/api";
import { Signature } from "@/components/brand/Signature";

export function MemoryView() {
  const [items, setItems] = useState<MemoryItem[] | null>(null);
  const [draft, setDraft] = useState("");
  const [adding, setAdding] = useState(false);

  const refresh = () => api.listMemories().then(setItems).catch(() => setItems([]));
  useEffect(() => {
    void refresh();
  }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const content = draft.trim();
    if (!content) return;
    setAdding(true);
    try {
      await api.createMemory(content);
      setDraft("");
      await refresh();
    } catch {
      /* list stays as-is */
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-6 py-10 md:px-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-gold/65">Vednix · workspace</p>
            <h1 className="mt-3 font-display text-4xl font-extrabold tracking-tight text-cream md:text-5xl">
              Long-term <span className="text-gold-gradient">memory.</span>
            </h1>
            <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted">
              Facts and preferences Vednix keeps across sessions — stored in SQLite on your
              machine, searchable, deletable, never sent anywhere.
            </p>
          </div>
          <Signature framed className="mt-4" />
        </div>

        <form
          onSubmit={add}
          className="glass-liquid mt-8 flex w-full max-w-xl items-center gap-2 rounded-full py-1.5 pl-5 pr-1.5 transition-colors duration-300 focus-within:border-gold/40"
        >
          <BrainCircuit className="h-4 w-4 shrink-0 text-faint" />
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Teach Vednix something… e.g. मुझे संक्षिप्त जवाब पसंद हैं"
            aria-label="Add a memory"
            maxLength={500}
            className="min-w-0 flex-1 bg-transparent text-sm text-cream placeholder:text-faint focus:outline-none"
          />
          <button
            type="submit"
            disabled={adding}
            aria-label="Save memory"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gold text-void transition-all duration-300 hover:bg-gold-bright hover:shadow-glow-gold disabled:opacity-60"
          >
            {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          </button>
        </form>

        <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.22em] text-faint">
          {items === null ? "loading…" : `${items.length} ${items.length === 1 ? "memory" : "memories"}`}
        </p>

        <div className="mt-4 space-y-2">
          {items === null ? (
            <>
              <div className="skeleton h-12 w-full" />
              <div className="skeleton h-12 w-full" />
            </>
          ) : items.length === 0 ? (
            <div className="glass flex flex-col items-center gap-3 rounded-2xl px-6 py-12 text-center">
              <BrainCircuit className="h-8 w-8 text-gold/50" />
              <p className="text-sm text-muted">Nothing remembered yet.</p>
              <p className="max-w-sm text-xs leading-relaxed text-faint">
                In any chat, say <code className="text-gold/80">remember that …</code> — or teach
                something with the bar above.
              </p>
            </div>
          ) : (
            items.map((item) => (
              <div
                key={item.id}
                className="glass group flex items-start gap-3 rounded-2xl px-4 py-3.5 transition-all duration-300 hover:border-gold/25"
              >
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-gold/30 bg-gradient-to-br from-gold/25 to-ember/10">
                  <BrainCircuit className="h-3.5 w-3.5 text-gold-bright" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold/60">
                    #{item.id} · {item.kind}
                  </span>
                  <span className="mt-0.5 block text-sm leading-snug text-cream/85">{item.content}</span>
                </span>
                <button
                  aria-label={`Forget memory ${item.id}`}
                  onClick={() =>
                    void api.deleteMemory(item.id).then(() =>
                      setItems((cur) => cur?.filter((i) => i.id !== item.id) ?? []),
                    )
                  }
                  className="rounded-lg p-1.5 text-faint opacity-0 transition-all duration-300 hover:bg-white/10 hover:text-danger group-hover:opacity-100"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
