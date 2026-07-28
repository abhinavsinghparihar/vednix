/**
 * The VEDNIX wordmark — the animated NEURAL V sigil + tracked caps.
 * Server-safe (no hooks): usable from loading screens, footers and client
 * chrome alike. The mark animates everywhere, always — it IS the brand.
 */

import { cn } from "@/lib/utils";
import { BRAND_NAME } from "@/lib/brand";
import { LogoMark } from "@/components/brand/LogoMark";

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark size={32} />
      <span className="font-display text-sm font-bold tracking-[0.32em] text-cream">
        {BRAND_NAME.replace(" AI", "").toUpperCase()}
      </span>
    </span>
  );
}
