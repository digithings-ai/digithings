"use client";
/**
 * Theme controller for the React marketing apps. Sets [data-theme] on <html>
 * and persists the shared `dt-theme` key (also read by Olympus → cross-surface
 * sync on the same origin). Pair with the pre-paint snippet (themeInitScript)
 * inlined in <head> to avoid a flash.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

type Theme = "light" | "dark";
const KEY = "dt-theme";

/** Inline in <head> before paint: <script dangerouslySetInnerHTML={{__html: themeInitScript}}/> */
export const themeInitScript =
  "try{var s=localStorage.getItem('dt-theme');document.documentElement.setAttribute('data-theme',s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'))}catch(e){document.documentElement.setAttribute('data-theme','dark')}";

const ThemeCtx = createContext<{ theme: Theme; toggle: () => void } | null>(null);

export function useTheme() {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const current = (document.documentElement.getAttribute("data-theme") as Theme) || "dark";
    setTheme(current);
    const mq = matchMedia("(prefers-color-scheme: light)");
    const onOS = (e: MediaQueryListEvent) => {
      try { if (localStorage.getItem(KEY)) return; } catch {}
      const t = e.matches ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", t);
      setTheme(t);
    };
    mq.addEventListener("change", onOS);
    return () => mq.removeEventListener("change", onOS);
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem(KEY, next); } catch {}
      return next;
    });
  }, []);

  return <ThemeCtx.Provider value={{ theme, toggle }}>{children}</ThemeCtx.Provider>;
}

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle colour theme"
      title="Toggle theme"
      className={className ?? "theme-toggle"}
    >
      {theme === "dark" ? (
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round">
          <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
        </svg>
      )}
    </button>
  );
}
