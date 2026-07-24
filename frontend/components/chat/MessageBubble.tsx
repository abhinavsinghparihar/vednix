/**
 * One message row: user (right, gold-tinted glass) / assistant (left, orb
 * avatar, rich markdown) / system notices. Copy for all; regenerate for the
 * latest assistant reply; edit copies a user message into the composer.
 */

"use client";

import { memo, useState } from "react";
import { motion } from "framer-motion";
import { Check, Copy, Pencil, RotateCcw, Puzzle, Volume2, VolumeX } from "lucide-react";
import { useChat, useDisplayCoreState, type ChatMessage } from "@/store/chat";
import { cn } from "@/lib/utils";
import { Markdown } from "./Markdown";
import { Orb } from "@/components/orb/Orb";
import { Badge } from "@/components/ui/primitives";
import { AttachmentChipView } from "@/components/composer/Composer";
import { BookOpen, Globe } from "lucide-react";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      aria-label="Copy message"
      className="rounded-md p-1.5 text-muted transition-colors hover:bg-white/5 hover:text-gold-bright"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch { /* non-secure context */ }
      }}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

export const MessageBubble = memo(function MessageBubble({
  message,
  isLastAssistant,
}: {
  message: ChatMessage;
  isLastAssistant: boolean;
}) {
  const { send, speakMessage, voiceState } = useChat();
  const coreState = useDisplayCoreState();

  if (message.role === "system") {
    return (
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="mx-auto my-3 max-w-lg rounded-xl border border-[rgba(232,132,60,0.3)] bg-[rgba(232,132,60,0.08)] px-4 py-2 text-center text-xs text-ember/90"
      >
        {message.content}
      </motion.p>
    );
  }

  const isUser = message.role === "user";

  return (
    <motion.div
      layout="position"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      className={cn("group flex w-full gap-3", isUser && "flex-row-reverse")}
    >
      {!isUser && (
        <div className="mt-0.5 shrink-0">
          <Orb state={message.streaming ? coreState : "IDLE"} size={30} />
        </div>
      )}

      <div className={cn("flex min-w-0 max-w-[82%] flex-col", isUser && "items-end")}>
        {message.attachments && message.attachments.length > 0 && (
          <div className={cn("mb-1.5 flex flex-wrap gap-1.5", isUser && "justify-end")}>
            {message.attachments.map((att) => (
              <AttachmentChipView key={att.id} att={att} />
            ))}
          </div>
        )}
        <div
          className={cn(
            "rounded-2xl px-4 py-3",
            isUser
              ? "gold-border rounded-br-md text-cream"
              : "glass rounded-bl-md",
            message.error && "border-[rgba(240,86,79,0.4)]",
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{message.content}</p>
          ) : message.content ? (
            <Markdown content={message.content} />
          ) : (
            <span className="flex gap-1.5 py-1" aria-label="Vednix is thinking">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1.5 w-1.5 animate-bounce rounded-full bg-gold/80"
                  style={{ animationDelay: `${i * 140}ms` }}
                />
              ))}
            </span>
          )}
          {message.streaming && message.content && (
            <span className="ml-1 inline-block h-4 w-[7px] animate-pulse-soft rounded-sm bg-gold align-text-bottom" />
          )}
        </div>

        <div
          className={cn(
            "mt-1 flex items-center gap-1 px-1 opacity-0 transition-opacity group-hover:opacity-100",
            message.streaming && "opacity-0!",
          )}
        >
          <CopyButton text={message.content} />
          {!isUser && message.content && (
            <button
              aria-label={voiceState === "speaking" ? "Stop voice playback" : "Read aloud"}
              title={voiceState === "speaking" ? "Stop voice" : "Read aloud"}
              className={cn(
                "rounded-md p-1.5 transition-colors hover:bg-white/5",
                voiceState === "speaking" ? "text-gold" : "text-muted hover:text-gold-bright",
              )}
              onClick={() => speakMessage(message.id)}
            >
              {voiceState === "speaking" ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
            </button>
          )}
          {isUser && (
            <button
              aria-label="Edit into composer"
              title="Edit into composer"
              className="rounded-md p-1.5 text-muted transition-colors hover:bg-white/5 hover:text-gold-bright"
              onClick={() => window.dispatchEvent(new CustomEvent("vednix:edit", { detail: message.content }))}
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
          )}
          {isLastAssistant && !message.streaming && (
            <button
              aria-label="Regenerate"
              title="Regenerate from last prompt"
              className="rounded-md p-1.5 text-muted transition-colors hover:bg-white/5 hover:text-gold-bright"
              onClick={() => {
                const msgs = useChat.getState().messages;
                const lastUser = [...msgs].reverse().find((m) => m.role === "user");
                if (lastUser) send(lastUser.content);
              }}
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          )}
          {message.plugins.length > 0 && (
            <Badge className="ml-1 border-white/10 bg-white/[0.04] text-muted normal-case">
              <Puzzle className="mr-1 h-2.5 w-2.5" />{message.plugins.join(" + ")}
            </Badge>
          )}
          {message.kbSources && message.kbSources.length > 0 && (
            <Badge className="ml-1 border-[rgba(227,184,87,0.3)] bg-[rgba(227,184,87,0.08)] text-gold/90 normal-case">
              <BookOpen className="mr-1 h-2.5 w-2.5" />{message.kbSources.join(" · ")}
            </Badge>
          )}
        </div>
        {message.sources && message.sources.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-white/5 pt-2">
            <span className="text-[10px] uppercase tracking-[0.14em] text-faint">Sources</span>
            {message.sources.map((s, i) => (
              <a
                key={`${s.url}-${i}`}
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex max-w-[240px] items-center gap-1 rounded-full border border-[rgba(227,184,87,0.25)] bg-[rgba(227,184,87,0.06)] px-2 py-0.5 text-[11px] text-gold/90 transition-colors hover:bg-[rgba(227,184,87,0.14)]"
                title={s.url}
              >
                <Globe className="h-2.5 w-2.5 shrink-0" />
                <span className="truncate">[{i + 1}] {s.title}</span>
              </a>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
});

