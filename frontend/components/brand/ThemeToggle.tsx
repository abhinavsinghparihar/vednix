/**
 * Theme toggle — sun/moon with a soft rotate-fade swap between
 * "Vednix Obsidian" and "Vednix Ivory". Hydration-safe: renders neutral
 * until mounted (theme is a DOM property, not server state).
 */

"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Moon, Sun } from "lucide-react";
import { currentTheme, toggleTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => setTheme(currentTheme()), []);

  return (
    <button
      aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
      title={theme === "light" ? "Dark mode" : "Light mode"}
      onClick={() => setTheme(toggleTheme())}
      className={cn(
        "relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-white/5 text-muted transition-colors duration-300 hover:border-gold/40 hover:text-gold-bright",
        className,
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme ?? "pending"}
          initial={{ rotate: -70, opacity: 0, scale: 0.6 }}
          animate={{ rotate: 0, opacity: 1, scale: 1 }}
          exit={{ rotate: 70, opacity: 0, scale: 0.6 }}
          transition={{ duration: 0.28 }}
          className="flex"
        >
          {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
