/**
 * Knowledge view — the full-page home of the document base (promoted from
 * the studio panel's small section). Index documents, test-drive the FTS5
 * search yourself, and prune — all against the real /api/knowledge endpoints.
 */

"use client";

import { useRef, useState, useEffect } from "react";
import { BookOpen, FileText, Loader2, RefreshCw, Search, Trash2 } from "lucide-react";
import { api, type KnowledgeDoc, type KnowledgeHit } from "@/lib/api";
import { Signature } from "@/components/brand/Signature";

/** render FTS5 «marked» terms as gold highlights */
function Snippet({ text }: { text: string }) {
  const parts = text.split(/«|»/);
  return (
    <span className="leading-relaxed text-cream/85">
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="rounded bg-gold/25 px-0.5 text-gold-bright">
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </span>
  );
}

export function KnowledgeView() {
  const [docs, setDocs] = useState<KnowledgeDoc[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<KnowledgeHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () => api.listKnowledgeDocs().then(setDocs).catch(() => setDocs([]));
  useEffect(() => {
    void refresh();
  }, []);

  const addFiles = async (files: FileList) => {
    setBusy(true);
    try {
      const uploaded = await api.uploadFiles(Array.from(files));
      for (const u of uploaded) {
        await api.addKnowledgeDoc({ uploaded_file_id: u.id, title: u.name });
      }
      await refresh();
    } catch {
      /* panel stays usable; failures surface in console */
    } finally {
      setBusy(false);
    }
  };

  const runSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    setSearching(true);
    try {
      const res = await api.searchKnowledge(q.trim());
      setHits(res.hits);
    } catch {
      setHits([]);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-6 py-10 md:px-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-gold/65">Vednix · workspace</p>
            <h1 className="mt-3 font-display text-4xl font-extrabold tracking-tight text-cream md:text-5xl">
              Knowledge <span className="text-gold-gradient">base.</span>
            </h1>
            <p className="mt-3 max-w-lg text-sm leading-relaxed text-muted">
              Documents indexed here are searched automatically and cited into chat answers —
              on-device FTS5 + BM25, with «snippets» proving where answers came from.
            </p>
          </div>
          <Signature framed className="mt-4" />
        </div>

        <input
          ref={fileRef}
          type="file"
          hidden
          multiple
          accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.pptx"
          onChange={(e) => {
            if (e.target.files?.length) void addFiles(e.target.files);
            e.target.value = "";
          }}
        />

        {/* test-drive the search */}
        <form
          onSubmit={runSearch}
          className="glass-liquid mt-8 flex w-full max-w-xl items-center gap-2 rounded-full py-1.5 pl-5 pr-1.5 transition-colors duration-300 focus-within:border-gold/40"
        >
          <Search className="h-4 w-4 shrink-0 text-faint" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search inside your documents…"
            aria-label="Search knowledge base"
            className="min-w-0 flex-1 bg-transparent text-sm text-cream placeholder:text-faint focus:outline-none"
          />
          <button
            type="submit"
            disabled={searching}
            aria-label="Run search"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gold text-void transition-all duration-300 hover:bg-gold-bright hover:shadow-glow-gold disabled:opacity-60"
          >
            {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          </button>
        </form>

        {hits !== null && (
          <div className="mt-4 max-w-xl space-y-2">
            <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-faint">
              {hits.length} {hits.length === 1 ? "hit" : "hits"}
            </p>
            {hits.map((h) => (
              <div key={h.chunk_id} className="glass rounded-xl px-4 py-3 text-xs">
                <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.16em] text-gold/70">
                  {h.document}
                </p>
                <Snippet text={h.snippet} />
              </div>
            ))}
            {hits.length === 0 && (
              <p className="text-xs text-faint">Nothing matched — try different terms.</p>
            )}
          </div>
        )}

        {/* documents */}
        <div className="mt-10 flex items-center justify-between">
          <p className="font-mono text-[10px] uppercase tracking-[0.26em] text-faint">
            Indexed documents {docs ? `· ${docs.length}` : ""}
          </p>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="flex items-center gap-2 rounded-xl bg-gold px-4 py-2 text-[11px] font-bold uppercase tracking-[0.12em] text-void transition-all duration-300 hover:bg-gold-bright hover:shadow-glow-gold disabled:opacity-60"
          >
            {busy ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <BookOpen className="h-3.5 w-3.5" />}
            Add document
          </button>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
          {docs === null ? (
            <>
              <div className="skeleton h-16 w-full" />
              <div className="skeleton h-16 w-full" />
            </>
          ) : docs.length === 0 ? (
            <div className="glass col-span-full flex flex-col items-center gap-3 rounded-2xl px-6 py-12 text-center">
              <FileText className="h-8 w-8 text-gold/50" />
              <p className="text-sm text-muted">Nothing indexed yet.</p>
              <p className="max-w-sm text-xs leading-relaxed text-faint">
                Drop in a handbook, notes, or a spec — PDF, DOCX, XLSX, PPTX, CSV or plain text —
                and Vednix will cite it in answers.
              </p>
            </div>
          ) : (
            docs.map((d) => (
              <div
                key={d.id}
                className="glass group flex items-center gap-3 rounded-2xl px-4 py-3.5 transition-all duration-300 hover:-translate-y-0.5 hover:border-gold/25"
              >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-gold/30 bg-gradient-to-br from-gold/25 to-ember/10">
                  <FileText className="h-4 w-4 text-gold-bright" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-cream/90">{d.title}</span>
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
                    {d.chunk_count} chunks
                  </span>
                </span>
                <button
                  aria-label={`Remove ${d.title}`}
                  onClick={() => void api.deleteKnowledgeDoc(d.id).then(refresh)}
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
