/**
 * The Vednix Orb — direct port of dev_ai/ui/orb.py's design (audit §10: "same
 * soul, new code"). All 8 CoreStates now actually fire (they were unreachable
 * in the desktop app — audit U6). Gold luxury palette, WebGL-free canvas, 60fps.
 */

"use client";

import { useEffect, useRef } from "react";
import type { CoreStateName } from "@/lib/ws";
import { cn } from "@/lib/utils";

const GOLD = "#e3b857";
const GOLD_BRIGHT = "#f4d68a";
const GOLD_DIM = "#8a6d2f";
const EMBER = "#e8843c";
const CREAM = "#fff4d6";

interface OrbProps {
  state: CoreStateName;
  size?: number;
  className?: string;
}

export function Orb({ state, size = 130, className }: OrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<CoreStateName>(state);
  stateRef.current = state;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cx = size / 2;
    const cy = size / 2;
    let tick = 0;
    let raf = 0;

    const ring = (r: number, color: string, width = 2, alpha = 1) => {
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    };

    const core = (r: number, color: string, glow = 18) => {
      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = glow;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    };

    const dot = (x: number, y: number, r: number, color: string) => {
      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = 10;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    };

    const s = size / 130; // scale factor relative to design size

    const painters: Record<CoreStateName, () => void> = {
      IDLE: () => {
        const pulse = (Math.sin(tick * 0.03) + 1) / 2;
        const r = (30 + pulse * 5) * s;
        ring(r + 14 * s, GOLD_DIM, 1, 0.55);
        core(r, GOLD_DIM, 10);
        core(r * 0.52, GOLD, 16);
      },
      LISTENING: () => {
        const pulse = (Math.sin(tick * 0.15) + 1) / 2;
        const r = (32 + pulse * 8) * s;
        ring(r + 11 * s, GOLD_BRIGHT, 2);
        core(r, GOLD, 18);
        core(r * 0.4, CREAM, 12);
      },
      THINKING: () => {
        core(28 * s, GOLD_DIM, 8);
        for (let i = 0; i < 8; i++) {
          const angle = tick * 0.06 + (i * Math.PI) / 4;
          dot(cx + Math.cos(angle) * 48 * s, cy + Math.sin(angle) * 48 * s, 3.2 * s, i % 3 === 0 ? EMBER : GOLD);
        }
      },
      SPEAKING: () => {
        const base = 30 * s;
        for (let i = 0; i < 3; i++) {
          const wobble = Math.sin(tick * 0.3 + i * 1.4) * 9 * s;
          ring(base + i * 11 * s + wobble, GOLD_BRIGHT, 1.6, 0.85 - i * 0.22);
        }
        core(base * 0.72, GOLD, 16);
      },
      EXECUTING: () => {
        ring(48 * s, GOLD, 2.5);
        const angle = tick * 0.1;
        dot(cx + Math.cos(angle) * 48 * s, cy + Math.sin(angle) * 48 * s, 4.5 * s, CREAM);
        core(26 * s, GOLD_DIM, 10);
      },
      SEARCHING: () => {
        ring(50 * s, GOLD_DIM, 1, 0.6);
        const angle = tick * 0.12;
        ctx.save();
        ctx.strokeStyle = GOLD_BRIGHT;
        ctx.lineWidth = 2;
        ctx.shadowColor = GOLD;
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(angle) * 50 * s, cy + Math.sin(angle) * 50 * s);
        ctx.stroke();
        ctx.restore();
        core(26 * s, GOLD_DIM, 8);
      },
      UPDATING: () => {
        const on = Math.floor(tick / 4) % 2 === 0;
        ring(42 * s, on ? GOLD : GOLD_DIM, 2);
        core(30 * s, on ? GOLD : GOLD_DIM, on ? 16 : 6);
      },
      LEARNING: () => {
        for (const [i, radius] of [26, 39, 52].entries()) {
          const dir = i % 2 === 0 ? 1 : -1;
          const offset = Math.sin(tick * (0.02 + i * 0.01) * dir) * 3.5 * s;
          ring(radius * s + offset, GOLD_DIM, 1, 0.75 - i * 0.18);
        }
        core(21 * s, GOLD, 14);
      },
    };

    const frame = () => {
      tick += 1;
      ctx.clearRect(0, 0, size, size);
      (painters[stateRef.current] ?? painters.IDLE)();
      if (!reduced) raf = requestAnimationFrame(frame);
    };
    frame();

    return () => cancelAnimationFrame(raf);
  }, [size]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size }}
      className={cn("select-none", state !== "IDLE" && "drop-shadow-[0_0_18px_rgba(227,184,87,0.35)]", className)}
      role="img"
      aria-label={`Vednix AI orb — ${state.toLowerCase()}`}
    />
  );
}
