/**
 * Scrollable message stream. Keep-pinned-to-bottom while streaming when the
 * user is already near the bottom; smooth, deferred rendering during tokens.
 */

"use client";

import { useDeferredValue, useEffect, useRef } from "react";
import { useChat } from "@/store/chat";
import { MessageBubble } from "./MessageBubble";

export function ChatView() {
  const messages = useChat((s) => s.messages);
  const loading = useChat((s) => s.loadingMessages);
  const deferred = useDeferredValue(messages); // token bursts never jank scroll
  const scrollerRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  const lastAssistantId = [...deferred].reverse().find((m) => m.role === "assistant")?.id;

  useEffect(() => {
    const el = scrollerRef.current;
    if (el && pinnedRef.current) {
      el.scrollTo({ top: el.scrollHeight, behavior: "instant" as ScrollBehavior });
    }
  }, [deferred]);

  return (
    <div
      ref={scrollerRef}
      onScroll={(e) => {
        const el = e.currentTarget;
        pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
      }}
      className="no-scrollbar relative flex-1 overflow-y-auto px-4 md:px-8"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-5 py-6">
        {loading ? (
          <div className="space-y-4 pt-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className={i % 2 ? "ml-auto w-2/3" : "w-3/4"}>
                <div className="skeleton h-16 w-full" />
              </div>
            ))}
          </div>
        ) : (
          deferred.map((m) => (
            <MessageBubble key={m.id} message={m} isLastAssistant={m.id === lastAssistantId} />
          ))
        )}
      </div>
    </div>
  );
}
