/**
 * Global loading splash — shown during route transitions and slow first
 * loads. Wordmark, soft pulse, creator signature. Nothing else.
 */

import { Signature } from "@/components/brand/Signature";
import { Wordmark } from "@/components/brand/Wordmark";

export default function Loading() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-7 bg-void">
      <span className="animate-pulse-soft">
        <Wordmark />
      </span>
      <Signature framed />
    </div>
  );
}
