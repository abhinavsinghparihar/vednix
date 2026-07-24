/**
 * Topbar: panel toggles, conversation title (click to rename), live CoreState
 * label + mini orb — 6 of these states were unreachable in the desktop app.
 */

"use client";

import { useState } from "react";
import { PanelLeft, PanelRight, Pencil, Check } from "lucide-react";
import { useChat, useDisplayCoreState } from "@/store/chat";
import { Button } from "@/components/ui/primitives";
import { Orb } from "@/components/orb/Orb";
import { cn } from "@/lib/utils";

const STATE_STYLES: Record<string, string> = {
  IDLE: "text-faint",
  LISTENING: "text-gold",
  THINKING: "text-gold-bright",
  SPEAKING: "text-emerald-300",
  EXECUTING: "text-ember",
  SEARCHING: "text-sky-300",
  LEARNING: "text-violet-300",
  UPDATING: "text-gold",
};

export function Topbar() {
  const { toggleSidebar, togglePanel, activeId, conversations, renameConversation } = useChat();
  const coreState = useDisplayCoreState();
  const conv = conversations.find((c) => c.id === activeId);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const commit = () => {
    setEditing(false);
    if (conv && draft.trim()) void renameConversation(conv.id, draft);
  };

  return (
    <header className="flex items-center gap-2 px-3 py-2.5 md:px-4">
      <Button size="icon" variant="ghost" aria-label="Toggle sidebar" onClick={toggleSidebar}>
        <PanelLeft className="h-4 w-4" />
      </Button>

      <div className="mx-auto flex min-w-0 items-center gap-2">
        {editing && conv ? (
          <span className="flex items-center gap-1">
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commit();
                if (e.key === "Escape") setEditing(false);
              }}
              className="rounded-lg bg-black/40 px-2 py-1 text-sm text-cream outline-none ring-1 ring-gold/40"
            />
            <Button size="icon" variant="ghost" aria-label="Save title" onClick={commit}><Check className="h-3.5 w-3.5" /></Button>
          </span>
        ) : (
          <button
            className="group flex min-w-0 items-center gap-2 rounded-lg px-2 py-1 transition-colors hover:bg-white/[0.04]"
            onClick={() => {
              if (conv) {
                setDraft(conv.title);
                setEditing(true);
              }
            }}
            title={conv ? "Rename" : undefined}
          >
            <span className="truncate text-sm font-medium text-cream/90">
              {conv ? conv.title : "New conversation"}
            </span>
            {conv && <Pencil className="h-3 w-3 shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-100" />}
          </button>
        )}
      </div>

      <div className="flex items-center gap-2.5">
        <span className={cn("font-mono text-[10px] uppercase tracking-[0.24em] transition-colors", STATE_STYLES[coreState])}>
          {coreState}
        </span>
        <Orb state={coreState} size={34} />
        <Button size="icon" variant="ghost" aria-label="Toggle studio panel" onClick={togglePanel}>
          <PanelRight className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
