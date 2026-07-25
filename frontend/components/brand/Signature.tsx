/**
 * The creator's signature — "Made by Abhinav Singh". One component, one
 * visual language everywhere it appears: mono micro-caps, faint ink,
 * optionally framed by two gold hairlines. Never large, never loud —
 * an official signature, not an advertisement.
 */

import { cn } from "@/lib/utils";
import { CREATOR_SIGNATURE } from "@/lib/brand";

export function Signature({
  framed = false,
  className,
}: {
  framed?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex select-none items-center gap-2.5 font-mono text-[9px] font-medium uppercase tracking-[0.3em] text-faint",
        className,
      )}
    >
      {framed && <span aria-hidden className="h-px w-5 bg-gold/25" />}
      <span className="whitespace-nowrap">{CREATOR_SIGNATURE}</span>
      {framed && <span aria-hidden className="h-px w-5 bg-gold/25" />}
    </span>
  );
}
