/**
 * Floating liquid-glass navigation — a dark-gold reinterpretation of the
 * classic floating pill nav. Desktop links collapse into a full-screen
 * overlay with staggered oversized links on mobile.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUpRight, Menu, X } from "lucide-react";
import { EASE } from "./shared";
import { Signature } from "@/components/brand/Signature";
import { Wordmark } from "@/components/brand/Wordmark";

const LINKS = [
  { label: "Workspace", href: "/chat" },
  { label: "Capabilities", href: "#capabilities" },
  { label: "Enter", href: "#enter" },
];

export function LandingNav() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <motion.header
        initial={{ y: -24, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8, ease: EASE }}
        className="fixed inset-x-0 top-5 z-50 flex justify-center px-4"
      >
        <nav
          className="glass-strong flex h-14 w-full max-w-5xl items-center justify-between rounded-2xl pl-4 pr-2"
          aria-label="Primary"
        >
          <Link href="#top" aria-label="Vednix AI — back to top">
            <Wordmark />
          </Link>

          <div className="hidden items-center gap-9 md:flex">
            {LINKS.map((l) => (
              <Link
                key={l.label}
                href={l.href}
                className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted transition-colors duration-300 hover:text-gold-bright"
              >
                {l.label}
              </Link>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <Link
              href="/chat"
              className="group hidden h-10 items-center gap-2 rounded-xl bg-gold px-5 text-[11px] font-bold uppercase tracking-[0.14em] text-void transition-all duration-300 hover:bg-gold-bright hover:shadow-glow-gold sm:flex"
            >
              Launch App
              <ArrowUpRight className="h-3.5 w-3.5 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
            </Link>
            <button
              onClick={() => setOpen(true)}
              aria-label="Open menu"
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-cream transition-colors duration-300 hover:bg-white/10 md:hidden"
            >
              <Menu className="h-4 w-4" />
            </button>
          </div>
        </nav>
      </motion.header>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            className="fixed inset-0 z-[60] flex flex-col bg-void/95 backdrop-blur-xl md:hidden"
          >
            <div className="flex h-20 items-center justify-between px-6">
              <Wordmark />
              <button
                onClick={() => setOpen(false)}
                aria-label="Close menu"
                className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-cream"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex flex-1 flex-col items-start justify-center gap-7 px-8">
              {LINKS.map((l, i) => (
                <motion.div
                  key={l.label}
                  initial={{ opacity: 0, y: 24 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6, delay: 0.1 + i * 0.09, ease: EASE }}
                >
                  <Link
                    href={l.href}
                    onClick={() => setOpen(false)}
                    className="font-display text-5xl font-extrabold uppercase tracking-tight text-cream transition-colors duration-300 hover:text-gold-bright"
                  >
                    {l.label}
                  </Link>
                </motion.div>
              ))}
              <motion.div
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.4, ease: EASE }}
                className="pt-6"
              >
                <Link
                  href="/chat"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-2 rounded-xl bg-gold px-7 py-3.5 text-[11px] font-bold uppercase tracking-[0.14em] text-void"
                >
                  Launch App <ArrowUpRight className="h-3.5 w-3.5" />
                </Link>
              </motion.div>
            </div>
            <div className="px-8 pb-9">
              <Signature framed />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
