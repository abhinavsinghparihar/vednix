/**
 * Landing primitives: the shared motion language + micro-typography.
 * One easing curve across the whole page — cinematic, never bouncy:
 * entrances glide in and land softly (cubic-bezier 0.16, 1, 0.3, 1).
 */

"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export const EASE = [0.16, 1, 0.3, 1] as const;

/** Entrance: fade + rise, staggered via `delay`. Respects reduced motion. */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 26 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.9, delay, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Scroll-triggered variant for below-the-fold sections. */
export function RevealInView({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.8, delay, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Tiny tracked-out mono label — the quiet luxury voice of the page. */
export function MicroLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p
      className={cn(
        "font-mono text-[10px] font-medium uppercase tracking-[0.34em] text-gold/65",
        className,
      )}
    >
      {children}
    </p>
  );
}
