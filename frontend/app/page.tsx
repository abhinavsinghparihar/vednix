/**
 * Vednix AI workspace — the single-chat shell.
 * Layers: neural background · mouse glow · sidebar | stage (topbar, chat,
 * composer) | studio panel.
 */

"use client";

import { useEffect } from "react";
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

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  return (
    <main className="relative flex h-dvh w-full overflow-hidden bg-void">
      <NeuralBackground />
      <MouseGlow />

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
