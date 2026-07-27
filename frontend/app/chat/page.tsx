/**
 * Vednix AI workspace (/chat) — the AI-OS shell. The Rail docks the
 * surfaces; the stage switches between the Home hub, the chat experience,
 * the Knowledge base and Memory. Landing identity lives at /.
 */

"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { Settings2, UploadCloud, UserRound } from "lucide-react";
import { useChat } from "@/store/chat";
import { useAuth } from "@/store/auth";
import { EASE_CURVE } from "@/lib/utils";
import { NeuralBackground } from "@/components/background/NeuralBackground";
import { MouseGlow } from "@/components/background/MouseGlow";
import { Rail } from "@/components/workspace/Rail";
import { DashboardView } from "@/components/workspace/DashboardView";
import { KnowledgeView } from "@/components/workspace/KnowledgeView";
import { MemoryView } from "@/components/workspace/MemoryView";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { ChatView } from "@/components/chat/ChatView";
import { EmptyState } from "@/components/chat/EmptyState";
import { Composer } from "@/components/composer/Composer";
import { ControlPanel } from "@/components/controls/ControlPanel";
import { Topbar } from "@/components/Topbar";

function WorkspacePage() {
  const bootstrap = useChat((s) => s.bootstrap);
  const messages = useChat((s) => s.messages);
  const view = useChat((s) => s.view);
  const setView = useChat((s) => s.setView);
  const authBootstrap = useAuth((s) => s.bootstrap);
  const onboarding = useAuth((s) => s.onboarding);
  const router = useRouter();
  const params = useSearchParams();
  const [dragging, setDragging] = useState(false);
  const dragDepth = useState({ count: 0 })[0];

  useEffect(() => {
    void bootstrap();
    void (async () => {
      const status = await authBootstrap();
      // first-run incomplete → the ceremony owns the shell
      if (status.setup_complete === false) {
        router.replace("/onboarding");
        return;
      }
      // accounts exist + no session → the lock screen owns the shell
      if (useAuth.getState().session === "locked") {
        router.replace("/login?next=/chat");
      }
    })();
    // A pending ask-capsule hand-off (landing dashboard capsule) is explicit
    // intent to compose — honor it on hard arrivals too, where the store
    // booted fresh to the default "dash" view. Composer consumes the text.
    try {
      if (sessionStorage.getItem("vednix.ask")) setView("chat");
    } catch {
      /* storage unavailable — the workspace opens on the dashboard */
    }
  }, [bootstrap, setView, authBootstrap, router]);

  // deep links: /chat?view=knowledge (Settings links land here)
  useEffect(() => {
    const v = params.get("view");
    if (v === "dash" || v === "chat" || v === "knowledge" || v === "memory") setView(v);
  }, [params, setView]);

  const onDragEnter = useCallback((e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragDepth.count += 1;
    setDragging(true);
  }, [dragDepth]);

  const onDragLeave = useCallback(() => {
    dragDepth.count = Math.max(0, dragDepth.count - 1);
    if (dragDepth.count === 0) setDragging(false);
  }, [dragDepth]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragDepth.count = 0;
    setDragging(false);
    if (e.dataTransfer.files.length) void useChat.getState().uploadDrafts(e.dataTransfer.files);
  }, [dragDepth]);

  return (
    <main
      className="relative flex h-dvh w-full overscroll-none overflow-hidden bg-void"
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
    >
      <NeuralBackground />
      <MouseGlow />

      <AnimatePresence>
        {dragging && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          >
            <div className="gold-border flex flex-col items-center gap-3 rounded-3xl px-12 py-10">
              <UploadCloud className="h-10 w-10 text-gold" />
              <p className="text-lg font-semibold text-gold-bright">Drop files to attach</p>
              <p className="text-xs text-faint">PDF · DOCX · XLSX · PPTX · CSV · images</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <Rail />

      <AnimatePresence mode="wait">
        {view === "chat" ? (
          <motion.section
            key="chat"
            className="relative flex min-w-0 flex-1"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.35, ease: EASE_CURVE }}
          >
            <Sidebar />

            <div className="relative flex min-w-0 flex-1 flex-col">
              {/* shell glides in as one cinematic stagger (the P2 motion language) */}
              <motion.div
                initial={{ opacity: 0, y: -16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, delay: 0.05, ease: EASE_CURVE }}
              >
                <Topbar />
              </motion.div>

              {/* run-mode ribbons: demo locks the engine, guest is temporary */}
              {onboarding?.demo_active && (
                <div className="mx-4 mt-2 flex items-center justify-between gap-3 rounded-xl border border-gold/30 bg-gold/[0.06] px-4 py-2">
                  <p className="text-[12px] text-gold-bright">
                    Demo tour — explore everything; the AI stays off.
                  </p>
                  <Link href="/onboarding" className="inline-flex items-center gap-1 text-[11px] font-semibold text-gold-bright hover:underline">
                    <Settings2 className="h-3 w-3" /> Connect AI
                  </Link>
                </div>
              )}
              {!onboarding?.demo_active && onboarding?.mode === "guest" && (
                <div className="mx-4 mt-2 flex items-center justify-between gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-1.5">
                  <p className="flex items-center gap-1.5 text-[11px] text-faint">
                    <UserRound className="h-3 w-3" /> Guest session — history is temporary
                  </p>
                  <Link href="/profile" className="text-[11px] text-gold-bright hover:underline">
                    Manage
                  </Link>
                </div>
              )}

              <motion.div
                className="relative flex min-h-0 flex-1 flex-col"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.8, delay: 0.12, ease: EASE_CURVE }}
              >
                {messages.length === 0 ? <EmptyState /> : <ChatView />}
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.75, delay: 0.2, ease: EASE_CURVE }}
              >
                {onboarding?.demo_active ? (
                  <div className="mx-auto mb-4 w-full max-w-3xl px-4">
                    <div className="glass-strong flex items-center justify-between gap-4 rounded-3xl px-5 py-4">
                      <p className="text-sm text-muted">
                        The composer rests during the demo tour.
                      </p>
                      <Link href="/onboarding">
                        <span className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-b from-[#f4d68a] to-[#d9a83f] px-4 py-2 text-sm font-semibold text-[#1c1505]">
                          <Settings2 className="h-4 w-4" /> Connect AI
                        </span>
                      </Link>
                    </div>
                  </div>
                ) : (
                  <Composer />
                )}
              </motion.div>
            </div>

            <ControlPanel />
          </motion.section>
        ) : (
          <motion.div
            key={view}
            className="flex min-w-0 flex-1"
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.35, ease: EASE_CURVE }}
          >
            {view === "dash" && <DashboardView />}
            {view === "knowledge" && <KnowledgeView />}
            {view === "memory" && <MemoryView />}
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}

export default function Page() {
  return (
    <Suspense>
      <WorkspacePage />
    </Suspense>
  );
}
