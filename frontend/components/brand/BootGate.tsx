/**
 * The Vednix boot sequence — the "cool opening". Once per tab session:
 * the Orb ignites, the wordmark and creator's signature rise, a hairline
 * of gold fills, then the curtain sweeps up to reveal the product.
 * Skipped instantly for reduced-motion users and on repeat visits.
 * Click anywhere to skip.
 */

"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Orb } from "@/components/orb/Orb";
import { Wordmark } from "@/components/brand/Wordmark";
import { Signature } from "@/components/brand/Signature";
import { EASE_CURVE } from "@/lib/utils";

const BOOT_KEY = "vednix.booted";
const HOLD_MS = 2100;

export function BootGate() {
  const [show, setShow] = useState(false);

  // decide once: play the intro only on the first mount of the tab session
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    try {
      if (!reduced && sessionStorage.getItem(BOOT_KEY) !== "1") {
        sessionStorage.setItem(BOOT_KEY, "1");
        setShow(true);
      }
    } catch {
      if (!reduced) setShow(true); // no storage → still honor the intro
    }
  }, []);

  // auto-dismiss — a separate effect keyed on `show` (a stale-closure read
  // of `show` in the mount effect would leave the curtain up forever)
  useEffect(() => {
    if (!show) return;
    const t = setTimeout(() => setShow(false), HOLD_MS);
    return () => clearTimeout(t);
  }, [show]);

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          key="boot"
          exit={{ y: "-100%" }}
          transition={{ duration: 0.75, ease: EASE_CURVE }}
          onClick={() => setShow(false)}
          className="fixed inset-0 z-[100] flex cursor-pointer flex-col items-center justify-center gap-8 bg-void"
          aria-label="Vednix AI is starting"
          role="status"
        >
          {/* ambient ignition glow */}
          <motion.div
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1.1, ease: EASE_CURVE }}
            className="absolute h-[420px] w-[420px] rounded-full bg-[radial-gradient(circle,rgba(227,184,87,0.16),transparent_62%)] blur-2xl"
            aria-hidden
          />

          <motion.div
            initial={{ scale: 0.4, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 160, damping: 15, delay: 0.15 }}
          >
            <Orb state="LISTENING" size={96} />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.55, ease: EASE_CURVE }}
            className="scale-110"
          >
            <Wordmark />
          </motion.div>

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.7, delay: 0.8 }}
          >
            <Signature framed />
          </motion.div>

          {/* progress hairline */}
          <motion.div
            aria-hidden
            className="absolute bottom-16 h-px w-40 origin-left bg-gradient-to-r from-transparent via-gold to-transparent"
            initial={{ scaleX: 0, opacity: 0.9 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: HOLD_MS / 1000 - 0.5, delay: 0.3, ease: "easeInOut" }}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
