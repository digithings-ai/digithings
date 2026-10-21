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
import {
  applyDocumentTheme,
  normalizePalette,
  matchThemeStep,
  nextThemeStep,
  readThemeState,
  type PaletteName,
  type ResolvedTheme,
  type ThemePreference,
  type ThemeStep,
} from "../theme/apply-theme";
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

export type { PaletteName, ResolvedTheme, ThemePreference };

// themeInitScript lives in ./themeInit.ts (a plain module) — see there.
export { themeInitScript } from "./themeInit";

export type ThemeContextValue = {
  /** Resolved light/dark currently painted. Existing callers read this. */
  theme: ResolvedTheme;
  /** Advance one stop: default dark, default light, then each palette. */
  toggle: () => void;
  /** Stored mode. `auto` means `dt-theme` is absent and the OS is followed. */
  preference: ThemePreference;
  setTheme: (preference: ThemePreference) => void;
  /** `default` or one of the 32 DigiVoice palette ids. Stored in `dt-palette`. */
  palette: PaletteName;
  setPalette: (palette: string) => void;
  /** Paint one cycle stop (mode and palette together). */
  applyStep: (step: ThemeStep) => void;
};

const ThemeCtx = createContext<ThemeContextValue | null>(null);

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
  const [theme, setResolved] = useState<ResolvedTheme>("dark");
  const [preference, setPreference] = useState<ThemePreference>("auto");
  const [palette, setPaletteState] = useState<PaletteName>("default");

  useEffect(() => {
    // A pinned embed owns the document. Applying storage here would put a
    // visitor's palette back after the pin script cleared it.
    if (document.documentElement.getAttribute("data-theme-pin") === "1") return;
    // Mount READS the document; it never paints or writes. The pre-paint
    // script (themeInitScript) has already applied the stored mode and
    // palette on the surfaces that use it, and a surface that pins its own
    // document (digiquant.io paints dark and runs no themeInitScript) keeps
    // what it painted. Applying storage here flipped such a page to whatever
    // the dashboard last mirrored into `dt-theme` on the same origin, after
    // paint, and wrote both keys on surfaces that never wrote before.
    const root = document.documentElement;
    const initial = readThemeState();
    const painted: ResolvedTheme = root.getAttribute("data-theme") === "light" ? "light" : "dark";
    setPreference(initial.preference);
    setPaletteState(normalizePalette(root.getAttribute("data-palette")));
    setResolved(painted);
    const mq = matchMedia("(prefers-color-scheme: light)");
    const onOS = () => {
      const current = readThemeState();
      if (current.preference !== "auto") return;
      setResolved(applyDocumentTheme("auto", current.palette));
    };
    mq.addEventListener("change", onOS);
    return () => mq.removeEventListener("change", onOS);
  }, []);

  const setTheme = useCallback((next: ThemePreference) => {
    const current = readThemeState();
    setPreference(next);
    setResolved(applyDocumentTheme(next, current.palette));
  }, []);

  const setPalette = useCallback((next: string) => {
    const current = readThemeState();
    const resolved = applyDocumentTheme(current.preference, next);
    setPaletteState(readThemeState().palette);
    setResolved(resolved);
  }, []);

  const applyStep = useCallback((step: ThemeStep) => {
    const resolved = applyDocumentTheme(step.mode, step.palette);
    setPreference(step.mode);
    setPaletteState(step.palette);
    setResolved(resolved);
  }, []);

  const toggle = useCallback(() => {
    const current = readThemeState();
    applyStep(nextThemeStep(current.preference, current.palette, current.resolved));
  }, [applyStep]);

  const value = useMemo(
    () => ({ theme, toggle, preference, setTheme, palette, setPalette, applyStep }),
    [theme, toggle, preference, setTheme, palette, setPalette, applyStep],
  );

  return (
    <ThemeCtx.Provider value={value}>
      <DirectionProvider root dir={dir}>
        {children}
      </DirectionProvider>
    </ThemeCtx.Provider>
  );
}

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, preference, palette, toggle } = useTheme();
  const step = matchThemeStep(preference, palette, theme);
  return (
    <IconButton
      type="button"
      onClick={toggle}
      aria-label="Toggle colour theme"
      title={step.label}
      className={className ?? "theme-toggle"}
    >
      {theme === "dark" ? (
        <svg
          viewBox="0 0 24 24"
          width="17"
          height="17"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        >
          <circle cx="12" cy="12" r="4.2" />
          <path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M19.1 4.9l-1.8 1.8M6.7 17.3l-1.8 1.8" />
        </svg>
      ) : (
        <svg
          viewBox="0 0 24 24"
          width="17"
          height="17"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        >
          <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
        </svg>
      )}
    </IconButton>
  );
}
