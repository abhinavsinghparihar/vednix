/**
 * Theme engine — "Vednix Obsidian" (dark, default) ⇄ "Vednix Ivory" (light).
 * The initial theme is applied by a blocking inline script in layout.tsx
 * (before first paint, no flash); this module is the runtime toggle.
 */

export type Theme = "dark" | "light";

export const THEME_KEY = "vednix.theme";

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* private mode — session-only theme */
  }
}

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function toggleTheme(): Theme {
  const next: Theme = currentTheme() === "light" ? "dark" : "light";
  applyTheme(next);
  return next;
}
