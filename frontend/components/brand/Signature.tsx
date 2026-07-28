/**
 * The creator's signature — "Made by Abhinav Singh". One component, one
 * visual language everywhere it appears: mono micro-caps, framed by two
 * gold hairlines when asked — and since Phase 8, the text itself wears the
 * TIRANGA: saffron "Made" · white-band "by" · India-green "Abhinav Singh",
 * each tone tuned to stay legible on both Obsidian and Ivory.
 * Never large, never loud — an official signature, not an advertisement.
 */

import { cn } from "@/lib/utils";
import { CREATOR_SIGNATURE } from "@/lib/brand";

/** The tricolor body, exported so vertical/raw placements (the rail) match. */
export function TricolorSignatureText({ className }: { className?: string }) {
  return (
    <span className={cn("whitespace-nowrap", className)}>
      <span className="text-[#f0a03c]">Made</span>{" "}
      <span className="text-cream/65">by</span>{" "}
      <span className="text-[#2fbf62]">Abhinav Singh</span>
    </span>
  );
}

export function Signature({
  framed = false,
  className,
}: {
  framed?: boolean;
  className?: string;
}) {
  return (
    <span
      aria-label={CREATOR_SIGNATURE}
      className={cn(
        "inline-flex select-none items-center gap-2.5 font-mono text-[9px] font-medium uppercase tracking-[0.3em]",
        className,
      )}
    >
      {framed && <span aria-hidden className="h-px w-5 bg-gold/25" />}
      <TricolorSignatureText />
      {framed && <span aria-hidden className="h-px w-5 bg-gold/25" />}
    </span>
  );
}
