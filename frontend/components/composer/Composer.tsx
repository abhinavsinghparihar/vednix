/**
 * Glass composer: auto-growing textarea, Enter-to-send, char counter,
 * send/stop morph. Attach + mic sit disabled with phase badges — they are
 * honest roadmap placeholders (Phase 3/4), not fake buttons.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Paperclip, Mic, ArrowUp, Square } from "lucide-react";
import { MAX_CHARS, useChat } from "@/store/chat";
import { cn } from "@/lib/utils";
import { Badge, Button } from "@/components/ui/primitives";

export function Composer() {
  const { send, stop, generating, wsStatus, coreState } = useChat();
  const [value, setValue] = useState("");
  const areaRef = useRef<HTMLTextAreaElement>(null);

  // "edit message" copies text here
  useEffect(() => {
    const onEdit = (e: Event) => {
      setValue((e as CustomEvent<string>).detail);
      areaRef.current?.focus();
    };
    window.addEventListener("vednix:edit", onEdit);
    return () => window.removeEventListener("vednix:edit", onEdit);
  }, []);

  const autosize = useCallback(() => {
    const el = areaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(autosize, [value, autosize]);

  const submit = () => {
    const text = value.trim();
    if (!text) return;
    send(text);
    setValue("");
  };

  const over = value.length > MAX_CHARS * 0.95;

  return (
    <div className="px-4 pb-5 pt-1 md:px-8">
      <div className="mx-auto max-w-3xl">
        <div
          className={cn(
            "glass-strong flex items-end gap-2 rounded-3xl p-3 transition-shadow duration-300",
            "focus-within:border-[rgba(227,184,87,0.45)] focus-within:shadow-glow-gold",
            generating && "border-[rgba(227,184,87,0.3)]",
          )}
        >
          {/* attach — Phase 4 */}
          <div className="group relative">
            <Button size="icon" variant="ghost" aria-label="Attach file (Phase 4)" disabled>
              <Paperclip className="h-4 w-4" />
            </Button>
            <Badge className="pointer-events-none absolute -top-7 left-1/2 -translate-x-1/2 opacity-0 transition-opacity group-hover:opacity-100">
              Phase 4
            </Badge>
          </div>

          <textarea
            ref={areaRef}
            value={value}
            onChange={(e) => setValue(e.target.value.slice(0, MAX_CHARS))}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder={
              wsStatus === "open"
                ? "Message Vednix… (किसी भी भाषा में लिखिए)"
                : "Waiting for backend…"
            }
            className="no-scrollbar max-h-[200px] min-h-[40px] flex-1 resize-none bg-transparent px-1 py-2 text-[15px] leading-relaxed text-cream placeholder:text-faint focus:outline-none"
            aria-label="Message Vednix AI"
          />

          {value.length > 2000 && (
            <span className={cn("pb-2 text-[10px] tabular-nums", over ? "text-danger" : "text-faint")}>
              {value.length.toLocaleString()}/{MAX_CHARS.toLocaleString()}
            </span>
          )}

          {/* mic — Phase 3 */}
          <div className="group relative">
            <Button size="icon" variant="ghost" aria-label="Voice input (Phase 3)" disabled>
              <Mic className="h-4 w-4" />
            </Button>
            <Badge className="pointer-events-none absolute -top-7 left-1/2 -translate-x-1/2 opacity-0 transition-opacity group-hover:opacity-100">
              Phase 3
            </Badge>
          </div>

          {generating ? (
            <Button size="icon" variant="primary" aria-label="Stop generating" onClick={stop} className="h-10 w-10 rounded-2xl">
              <Square className="h-3.5 w-3.5 fill-current" />
            </Button>
          ) : (
            <Button
              size="icon"
              variant="primary"
              aria-label="Send"
              onClick={submit}
              disabled={!value.trim() || wsStatus !== "open"}
              className="h-10 w-10 rounded-2xl"
            >
              <ArrowUp className="h-4.5 w-4.5 h-[18px] w-[18px]" />
            </Button>
          )}
        </div>

        <p className="mt-2 flex items-center justify-center gap-2 text-center text-[10px] tracking-wide text-faint">
          <span className={cn("h-1 w-1 rounded-full", coreState === "IDLE" ? "bg-faint" : "bg-gold animate-pulse-soft")} />
          Vednix runs fully offline · replies mirror your language · verify important info
        </p>
      </div>
    </div>
  );
}
