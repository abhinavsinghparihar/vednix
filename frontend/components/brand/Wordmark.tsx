/**
 * The VEDNIX wordmark — gold-bevelled "V" in a squircle + tracked caps.
 * Server-safe (no hooks): usable from loading screens, footers and client
 * chrome alike.
 */

import { cn } from "@/lib/utils";
import { BRAND_NAME } from "@/lib/brand";

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <span className="flex h-8 w-8 items-center justify-center rounded-[10px] border border-gold/40 bg-gradient-to-br from-gold/20 to-ember/10 font-display text-base font-extrabold text-gold-bright shadow-glow-gold">
        V
      </span>
      <span className="font-display text-sm font-bold tracking-[0.32em] text-cream">
        {BRAND_NAME.replace(" AI", "").toUpperCase()}
      </span>
    </span>
  );
}
