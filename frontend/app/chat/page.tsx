/**
 * Vednix AI workspace (/chat) — the single-chat shell. The landing identity
 * lives at /. Layers: neural background · mouse glow · sidebar | stage
 * (topbar, chat, composer) | studio panel.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { UploadCloud } from "lucide-react";
import { useChat } from "@/store/chat";
import { NeuralBackground } from "@/components/background/NeuralBackground";
import { MouseGlow } from "@/components/background/MouseGlow";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { ChatView } from "@/components/chat/ChatView";
import { EmptyState } from "@/components/chat/EmptyState";
import { Composer } from "@/components/composer/Composer";
import { ControlPanel } from "@/components/controls/ControlPanel";
import { Topbar } from "@/components/Topbar";

export default function WorkspacePage() {
  const bootstrap = useChat((s) => s.bootstrap);
  const messages = useChat((s) => s.messages);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useState({ count: 0 })[0];

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

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

      <Sidebar />

      <section className="relative flex min-w-0 flex-1 flex-col">
        <Topbar />
        {messages.length === 0 ? <EmptyState /> : <ChatView />}
        <Composer />
      </section>

      <ControlPanel />
    </main>
  );
}
