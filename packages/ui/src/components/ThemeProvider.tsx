"use client";
/**
 * Theme + direction controller for the React marketing apps. Sets
 * [data-theme] on <html> and persists the shared `dt-theme` key (also read by
 * dashboard → cross-surface sync on the same origin). Pair with the pre-paint
 * snippet (themeInitScript) inlined in <head> to avoid a flash.
 *
 * Direction is opt-in: `ThemeProvider dir="rtl"` (default `"ltr"`) applies
 * `dir` to <html>, which is all the kit needs — every part is authored with
 * logical properties and `[[dir=rtl]]`-scoped art, so the whole tree mirrors
 * without touching a single page. `DirectionProvider` is the nested form: it
 * wraps a region in its own `dir` (and `root` applies to <html> instead), for
 * side-by-side or per-subtree direction.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { IconButton } from "../ui/icon-button";

/** Text direction. The kit defaults to `"ltr"`; RTL is always opt-in. */
export type Direction = "ltr" | "rtl";

const DirectionCtx = createContext<Direction>("ltr");

/** Current text direction of the surrounding `DirectionProvider` (default ltr). */
export function useDirection(): Direction {
  return useContext(DirectionCtx);
}

/**
 * Apply `dir` to a region. By default it renders a wrapper <div dir=…> and
 * provides `useDirection()`; with `root` it applies `dir` to <html> instead
 * (matching `ThemeProvider dir`) and renders children without a wrapper, so a
 * full app or page can flip direction. Either form resets the document to
 * `ltr` on unmount when `root` is used.
 */
export function DirectionProvider({
  dir = "ltr",
  root = false,
  className,
  children,
}: {
  dir?: Direction;
  /** Apply to <html> (whole document) rather than a wrapper element. */
  root?: boolean;
  className?: string;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!root) return;
    document.documentElement.setAttribute("dir", dir);
    return () => {
      document.documentElement.setAttribute("dir", "ltr");
    };
  }, [dir, root]);

  const value = useMemo(() => dir, [dir]);
  if (root) return <DirectionCtx.Provider value={value}>{children}</DirectionCtx.Provider>;
  return (
    <DirectionCtx.Provider value={value}>
      <div dir={dir} className={className}>
        {children}
      </div>
    </DirectionCtx.Provider>
  );
}

type Theme = "light" | "dark";
const KEY = "dt-theme";

/** Browser-chrome colour per theme; must match --bg in tokens.css. */
const THEME_BG: Record<Theme, string> = { light: "#FBFBF9", dark: "#0A0E0C" };

/**
 * Point the single <meta name="theme-color"> at the active theme's --bg so the
 * browser toolbar/status bar matches the page. Keying theme-color off
 * prefers-color-scheme instead leaves a dark bar above a light page (and vice
 * versa) whenever the OS scheme and the chosen site theme disagree.
 */
function applyThemeColor(t: Theme) {
  try {
    let m = document.querySelector('meta[name="theme-color"]');
    if (!m) {
      m = document.createElement("meta");
      m.setAttribute("name", "theme-color");
      document.head.appendChild(m);
    }
    m.setAttribute("content", THEME_BG[t]);
  } catch {}
}

/** Inline in <head> before paint: <script dangerouslySetInnerHTML={{__html: themeInitScript}}/> */
export const themeInitScript =
  "try{var s=localStorage.getItem('dt-theme');var t=s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');document.documentElement.setAttribute('data-theme',t);var c=t==='light'?'#FBFBF9':'#0A0E0C';var m=document.querySelector('meta[name=\"theme-color\"]');if(!m){m=document.createElement('meta');m.setAttribute('name','theme-color');document.head.appendChild(m)}m.setAttribute('content',c)}catch(e){document.documentElement.setAttribute('data-theme','dark')}";

const ThemeCtx = createContext<{ theme: Theme; toggle: () => void } | null>(null);

export function useTheme() {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

export function ThemeProvider({
  children,
  dir = "ltr",
}: {
  children: ReactNode;
  /** Text direction applied to <html>. Defaults to `"ltr"`; RTL is opt-in. */
  dir?: Direction;
}) {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    const current = (document.documentElement.getAttribute("data-theme") as Theme) || "dark";
    setTheme(current);
    const mq = matchMedia("(prefers-color-scheme: light)");
    const onOS = (e: MediaQueryListEvent) => {
      try { if (localStorage.getItem(KEY)) return; } catch {}
      const t = e.matches ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", t);
      applyThemeColor(t);
      setTheme(t);
    };
    mq.addEventListener("change", onOS);
    return () => mq.removeEventListener("change", onOS);
  }, []);

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      applyThemeColor(next);
      try { localStorage.setItem(KEY, next); } catch {}
      return next;
    });
  }, []);

  return (
    <ThemeCtx.Provider value={{ theme, toggle }}>
      <DirectionProvider root dir={dir}>
        {children}
      </DirectionProvider>
    </ThemeCtx.Provider>
  );
}

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme();
  return (
    <IconButton
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
    </IconButton>
  );
}
