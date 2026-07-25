/**
 * Glass sidebar: brand, new chat, live search, conversation list with
 * pin/rename/delete, backend health footer.
 */

"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { MessageSquarePlus, Pin, PinOff, Search, Trash2, Pencil, Check, X, Folder } from "lucide-react";
import { useChat } from "@/store/chat";
import { api, type ConversationSummary } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { Button, Input } from "@/components/ui/primitives";
import { Orb } from "@/components/orb/Orb";
import { Signature } from "@/components/brand/Signature";

function ConversationRow({ conv, active }: { conv: ConversationSummary; active: boolean }) {
  const { selectConversation, removeConversation, togglePin, renameConversation } = useChat();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conv.title);

  const commit = () => {
    setEditing(false);
    if (draft.trim() && draft !== conv.title) void renameConversation(conv.id, draft);
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -16 }}
      transition={{ duration: 0.16 }}
      className={cn(
        "group relative flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 transition-colors",
        active
          ? "bg-[rgba(227,184,87,0.10)] shadow-[inset_0_0_0_1px_rgba(227,184,87,0.28)]"
          : "hover:bg-white/[0.045]",
      )}
      onClick={() => void selectConversation(conv.id)}
    >
      {conv.pinned && <Pin className="h-3 w-3 shrink-0 -rotate-45 text-gold/70" />}

      <div className="min-w-0 flex-1">
        {editing ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") setEditing(false);
            }}
            onClick={(e) => e.stopPropagation()}
            className="w-full rounded-md bg-black/40 px-1.5 py-0.5 text-sm text-cream outline-none ring-1 ring-gold/40"
          />
        ) : (
          <p className="truncate text-sm text-cream/90">{conv.title}</p>
        )}
        <p className="mt-0.5 text-[11px] text-faint">{timeAgo(conv.updated_at)} · {conv.language}</p>
      </div>

      <div
        className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100"
        onClick={(e) => e.stopPropagation()}
      >
        {editing ? (
          <>
            <Button size="icon" variant="ghost" aria-label="Save name" onClick={commit}><Check className="h-3.5 w-3.5" /></Button>
            <Button size="icon" variant="ghost" aria-label="Cancel" onClick={() => setEditing(false)}><X className="h-3.5 w-3.5" /></Button>
          </>
        ) : (
          <>
            <Button size="icon" variant="ghost" aria-label="Rename" onClick={() => { setDraft(conv.title); setEditing(true); }}>
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button size="icon" variant="ghost" aria-label={conv.pinned ? "Unpin" : "Pin"} onClick={() => void togglePin(conv.id)}>
              {conv.pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
            </Button>
            <Button
              size="icon" variant="danger" aria-label="Delete"
              onClick={() => { if (window.confirm(`Delete “${conv.title}”?`)) void removeConversation(conv.id); }}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </>
        )}
      </div>
    </motion.div>
  );
}

export function Sidebar() {
  const { conversations, activeId, newChat, loadingConversations, wsStatus, ollamaAvailable, sidebarOpen, provider } = useChat();
  const providerLabel = provider === "openrouter" ? "OpenRouter" : "Ollama";
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q ? conversations.filter((c) => c.title.toLowerCase().includes(q)) : conversations;
    return [...list].sort((a, b) => Number(b.pinned) - Number(a.pinned));
  }, [conversations, query]);

  const folders = useMemo(
    () => [...new Set(conversations.map((c) => c.folder).filter((f): f is string => !!f))],
    [conversations],
  );

  return (
    <AnimatePresence>
      {sidebarOpen && (
        <motion.aside
          initial={{ x: -320, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: -320, opacity: 0 }}
          transition={{ type: "spring", stiffness: 320, damping: 32 }}
          className="glass-strong z-30 flex h-full w-[290px] shrink-0 flex-col rounded-r-3xl border-l-0 px-4 py-4
                     max-md:fixed max-md:left-0 max-md:top-0 max-md:rounded-none max-md:shadow-[0_0_80px_rgba(0,0,0,0.8)]"
        >
          {/* brand */}
          <div className="flex items-center gap-3 px-1 pb-4">
            <Orb state="IDLE" size={44} />
            <div>
              <p className="text-gold-gradient text-lg font-bold tracking-tight">Vednix AI</p>
              <p className="text-[10px] uppercase tracking-[0.22em] text-faint">next-gen workspace</p>
            </div>
          </div>

          <Button variant="primary" onClick={newChat} className="mb-3 w-full">
            <MessageSquarePlus className="h-4 w-4" /> New chat
          </Button>

          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-faint" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search chats…"
              className="pl-8"
            />
          </div>

          {/* conversation list */}
          <div className="no-scrollbar -mx-1 flex-1 overflow-y-auto px-1">
            {loadingConversations ? (
              <div className="space-y-2 pt-1">
                {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-12 w-full" />)}
              </div>
            ) : filtered.length === 0 ? (
              <p className="px-2 pt-6 text-center text-xs text-faint">
                {query ? "No chats match your search." : "No conversations yet — start one!"}
              </p>
            ) : (
              <AnimatePresence initial={false}>
                {filtered.map((conv) => (
                  <ConversationRow key={conv.id} conv={conv} active={conv.id === activeId} />
                ))}
              </AnimatePresence>
            )}

            {folders.length > 0 && (
              <div className="mt-4 border-t border-edge-soft pt-3">
                <p className="mb-1 flex items-center gap-1.5 px-2 text-[10px] uppercase tracking-widest text-faint">
                  <Folder className="h-3 w-3" /> Folders
                </p>
                {folders.map((f) => (
                  <p key={f} className="truncate px-3 py-1.5 text-xs text-muted">{f}</p>
                ))}
              </div>
            )}
          </div>

          {/* footer: health + creator signature */}
          <div className="mt-3 flex items-center justify-between rounded-xl bg-black/30 px-3 py-2 text-[11px] text-muted">
            <span className="flex items-center gap-1.5">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  wsStatus === "open" ? "bg-emerald-400 shadow-[0_0_6px_#34d399]" : "bg-red-400 animate-pulse-soft",
                )}
              />
              {wsStatus === "open" ? "Backend live" : wsStatus === "connecting" ? "Connecting…" : "Reconnecting…"}
            </span>
            <span className={cn(ollamaAvailable ? "text-gold/80" : "text-red-300/80")}>
              {providerLabel} {ollamaAvailable ? "✓" : "✕"}
            </span>
          </div>
          <div className="mt-2.5 flex justify-center pb-0.5">
            <Signature />
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
