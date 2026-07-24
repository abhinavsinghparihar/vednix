/**
 * Cursor-following gold halo — the "mouse glow" from the design brief.
 * rAF-throttled, blend-screen, disabled for touch/reduced-motion.
 */

"use client";

import { useEffect, useRef } from "react";

export function MouseGlow() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce), (pointer: coarse)").matches) return;

    let x = window.innerWidth / 2;
    let y = window.innerHeight / 3;
    let tx = x;
    let ty = y;
    let raf = 0;

    const onMove = (e: MouseEvent) => {
      tx = e.clientX;
      ty = e.clientY;
    };

    const frame = () => {
      // buttery lerp — glow trails the cursor
      x += (tx - x) * 0.09;
      y += (ty - y) * 0.09;
      el.style.transform = `translate3d(${x - 300}px, ${y - 300}px, 0)`;
      raf = requestAnimationFrame(frame);
    };

    window.addEventListener("mousemove", onMove, { passive: true });
    raf = requestAnimationFrame(frame);
    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed -z-10 h-[600px] w-[600px] rounded-full opacity-70 mix-blend-screen"
      style={{
        background:
          "radial-gradient(circle, rgba(227,184,87,0.075) 0%, rgba(227,184,87,0.02) 40%, transparent 70%)",
      }}
    />
  );
}
