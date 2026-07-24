/**
 * Ambient neural-network background: drifting gold particles linked by faint
 * synapses + warm vignette glows. Performance-budgeted: ~64 nodes, shared rAF
 * with the page, paused when the tab is hidden (audit-grade perf discipline).
 */

"use client";

import { useEffect, useRef } from "react";

interface Particle {
  x: number; y: number; vx: number; vy: number; r: number;
}

export function NeuralBackground() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) return;

    let width = 0;
    let height = 0;
    let raf = 0;
    let particles: Particle[] = [];
    const dpr = Math.min(2, window.devicePixelRatio || 1);

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.min(72, Math.round((width * height) / 26000));
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.22,
        vy: (Math.random() - 0.5) * 0.22,
        r: Math.random() * 1.5 + 0.5,
      }));
    };

    const LINK_DIST = 135;

    const frame = () => {
      ctx.clearRect(0, 0, width, height);

      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < -20) p.x = width + 20;
        if (p.x > width + 20) p.x = -20;
        if (p.y < -20) p.y = height + 20;
        if (p.y > height + 20) p.y = -20;
      }

      ctx.lineWidth = 1;
      for (let i = 0; i < particles.length; i++) {
        const a = particles[i];
        for (let j = i + 1; j < particles.length; j++) {
          const b = particles[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.hypot(dx, dy);
          if (dist < LINK_DIST) {
            const alpha = (1 - dist / LINK_DIST) * 0.13;
            ctx.strokeStyle = `rgba(227, 184, 87, ${alpha.toFixed(3)})`;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      for (const p of particles) {
        ctx.beginPath();
        ctx.fillStyle = "rgba(232, 196, 120, 0.4)";
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
      }

      raf = requestAnimationFrame(frame);
    };

    const onVisibility = () => {
      if (document.hidden) {
        cancelAnimationFrame(raf);
      } else {
        raf = requestAnimationFrame(frame);
      }
    };

    resize();
    frame();
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <>
      <canvas ref={ref} className="pointer-events-none fixed inset-0 -z-20" aria-hidden />
      {/* warm luxury vignettes */}
      <div className="pointer-events-none fixed -z-30 inset-0" aria-hidden>
        <div className="absolute -top-40 left-1/4 h-[480px] w-[480px] rounded-full bg-[radial-gradient(circle,rgba(227,184,87,0.07),transparent_65%)] blur-2xl" />
        <div className="absolute bottom-0 right-0 h-[520px] w-[520px] rounded-full bg-[radial-gradient(circle,rgba(232,132,60,0.05),transparent_65%)] blur-2xl" />
        <div className="absolute top-1/3 -left-32 h-[420px] w-[420px] rounded-full bg-[radial-gradient(circle,rgba(120,80,30,0.06),transparent_65%)] blur-2xl" />
      </div>
    </>
  );
}
