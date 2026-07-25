/**
 * Minimal footer — wordmark, the three promises, copyright. Nothing else.
 */

import Link from "next/link";
import { Wordmark } from "./LandingNav";

export function LandingFooter() {
  return (
    <footer className="border-t border-edge/60">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-center justify-between gap-5 px-6 py-9 sm:flex-row sm:px-10 lg:px-14">
        <Link href="#top" aria-label="Vednix AI — back to top">
          <Wordmark />
        </Link>
        <p className="font-mono text-[10px] uppercase tracking-[0.24em] text-faint">
          Offline-first · No telemetry · हिंदी-ready
        </p>
        <p className="font-mono text-[10px] tracking-[0.2em] text-faint">© 2026 VEDNIX AI</p>
      </div>
    </footer>
  );
}
