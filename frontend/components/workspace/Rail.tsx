/**
 * The Rail — Vednix's OS dock. A floating liquid-glass vertical strip that
 * switches between the workspace's surfaces: Home hub, Chat, Knowledge,
 * Memory. Bottom carries the theme toggle and the creator's signature in
 * vertical micro-type. Hidden on small screens (chat stays the mobile hero).
 */

"use client";

import Link from "next/link";
import { BookOpen, BrainCircuit, LayoutGrid, MessageSquare, Settings2, UserRound } from "lucide-react";
import { useChat, type WorkspaceView } from "@/store/chat";
import { ThemeToggle } from "@/components/brand/ThemeToggle";
import { LogoMark } from "@/components/brand/LogoMark";
import { TricolorSignatureText } from "@/components/brand/Signature";
import { cn } from "@/lib/utils";

const ITEMS: { view: WorkspaceView; label: string; icon: typeof LayoutGrid }[] = [
  { view: "dash", label: "Home", icon: LayoutGrid },
  { view: "chat", label: "Chat", icon: MessageSquare },
  { view: "knowledge", label: "Knowledge", icon: BookOpen },
  { view: "memory", label: "Memory", icon: BrainCircuit },
];

export function Rail() {
  const view = useChat((s) => s.view);
  const setView = useChat((s) => s.setView);

  return (
    <nav
      aria-label="Workspace views"
      className="glass-liquid z-30 m-3 ml-3 mr-0 hidden w-[62px] shrink-0 flex-col items-center gap-2 rounded-3xl py-4 md:flex"
    >
      {/* the neural V — animated, always */}
      <LogoMark size={38} className="mb-2" />

      {ITEMS.map((it) => {
        const active = view === it.view;
        return (
          <button
            key={it.view}
            onClick={() => setView(it.view)}
            aria-label={it.label}
            title={it.label}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex h-11 w-11 items-center justify-center rounded-2xl transition-all duration-300",
              active
                ? "bg-gold/15 text-gold shadow-[inset_0_0_0_1px_rgba(227,184,87,0.35)]"
                : "text-muted hover:bg-white/[0.05] hover:text-cream",
            )}
          >
            <it.icon className="h-[18px] w-[18px]" />
          </button>
        );
      })}

      <div className="mt-auto flex flex-col items-center gap-3">
        <span className="h-px w-7 bg-white/[0.08]" />
        <Link
          href="/settings"
          aria-label="Settings"
          title="Settings"
          className="flex h-10 w-10 items-center justify-center rounded-2xl text-muted transition-all duration-300 hover:bg-white/[0.05] hover:text-cream"
        >
          <Settings2 className="h-[17px] w-[17px]" />
        </Link>
        <Link
          href="/profile"
          aria-label="Profile"
          title="Profile"
          className="flex h-10 w-10 items-center justify-center rounded-2xl text-muted transition-all duration-300 hover:bg-white/[0.05] hover:text-cream"
        >
          <UserRound className="h-[17px] w-[17px]" />
        </Link>
        <ThemeToggle />
        <span
          aria-label="Made by Abhinav Singh"
          className="font-mono text-[8px] uppercase tracking-[0.26em] [writing-mode:vertical-rl]"
        >
          <TricolorSignatureText />
        </span>
      </div>
    </nav>
  );
}
