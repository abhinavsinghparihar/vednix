/**
 * Vednix AI workspace (/chat) — the AI-OS shell. The Rail docks the
 * surfaces; the stage switches between the Home hub, the chat experience,
 * the Knowledge base and Memory. Landing identity lives at /.
 */

"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { UploadCloud } from "lucide-react";
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
      // NO SIGNUP, NO ENTRY — the lock screen owns the shell
      if (useAuth.getState().session !== "authed") {
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
                <Composer />
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
