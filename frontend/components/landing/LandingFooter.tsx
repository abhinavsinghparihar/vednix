/**
 * Minimal footer — wordmark, the creator's signature framed in gold
 * hairlines, and the promises. Nothing else.
 */

import Link from "next/link";
import { CreatorLinks } from "@/components/brand/CreatorLinks";
import { Signature } from "@/components/brand/Signature";
import { Wordmark } from "@/components/brand/Wordmark";

export function LandingFooter() {
  return (
    <footer className="border-t border-edge/60">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-center justify-between gap-5 px-6 py-9 sm:flex-row sm:px-10 lg:px-14">
        <Link href="#top" aria-label="Vednix AI — back to top">
          <Wordmark />
        </Link>
        <div className="flex flex-col items-center gap-2">
          <Signature framed />
          <CreatorLinks />
        </div>
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-faint">
          Private-first · No telemetry · © 2026
        </p>
      </div>
    </footer>
  );
}
