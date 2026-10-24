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
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  applyDocumentTheme,
  matchThemeStep,
  nextThemeStep,
  readPaintedTheme,
  readThemeState,
  THEME_CHANGE_EVENT,
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
  const [preference, setPreferenceState] = useState<ThemePreference>("auto");
  const [palette, setPaletteState] = useState<PaletteName>("default");
  const preferenceRef = useRef<ThemePreference>("auto");
  const setPreference = useCallback((next: ThemePreference) => {
    preferenceRef.current = next;
    setPreferenceState(next);
  }, []);

  useEffect(() => {
    // The document is the source of truth; storage is only where a user's
    // choice is kept. Mount READS what is painted and never paints or writes:
    // themeInitScript has already applied the stored mode and palette on the
    // surfaces that use it, a pinned embed (data-theme-pin) painted its
    // tenant's theme, and digiquant.io paints dark itself with no
    // themeInitScript. Applying storage here flipped such a page to whatever
    // the dashboard last mirrored into `dt-theme` on that origin.
    const sync = () => {
      const painted = readPaintedTheme();
      const stored = readThemeState().preference;
      // A stored mode the page did not paint (a pinned surface) is not this
      // page's preference; the painted mode is.
      setPreference(stored === "auto" || stored === painted.resolved ? stored : painted.resolved);
      setPaletteState(painted.palette);
      setResolved(painted.resolved);
    };
    sync();
    // A pinned embed owns its document: no OS follow there.
    if (document.documentElement.getAttribute("data-theme-pin") === "1") return;
    // Any painter (the /theme command, the picker, this provider) goes through
    // applyDocumentTheme, which announces the change; re-read so the context
    // and the OS guard below never disagree with what is painted.
    window.addEventListener(THEME_CHANGE_EVENT, sync);
    const mq = matchMedia("(prefers-color-scheme: light)");
    const onOS = () => {
      // As before this provider existed: a stored mode means a choice was
      // made, so the OS does not override it.
      if (readThemeState().preference !== "auto") return;
      // Repaint only; the OS changing is not a choice to store.
      setResolved(
        applyDocumentTheme("auto", readPaintedTheme().palette, undefined, { persist: false }),
      );
    };
    mq.addEventListener("change", onOS);
    return () => {
      window.removeEventListener(THEME_CHANGE_EVENT, sync);
      mq.removeEventListener("change", onOS);
    };
  }, [setPreference]);

  const setTheme = useCallback(
    (next: ThemePreference) => {
      setPreference(next);
      setResolved(applyDocumentTheme(next, readPaintedTheme().palette));
    },
    [setPreference],
  );

  const setPalette = useCallback((next: string) => {
    const resolved = applyDocumentTheme(preferenceRef.current, next);
    setPaletteState(readPaintedTheme().palette);
    setResolved(resolved);
  }, []);

  const applyStep = useCallback(
    (step: ThemeStep) => {
      const resolved = applyDocumentTheme(step.mode, step.palette);
      setPreference(step.mode);
      setPaletteState(step.palette);
      setResolved(resolved);
    },
    [setPreference],
  );

  const toggle = useCallback(() => {
    const painted = readPaintedTheme();
    applyStep(nextThemeStep("auto", painted.palette, painted.resolved));
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

/**
 * Theme control for the nav tail.
 *
 * One glyph, not two: the control moves through *theme* (default dark, default
 * light, then 32 palettes), so a sun/moon pair only ever described two stops of
 * a longer cycle and read as a mode switch that it is not. The contrast mark —
 * a ring with half of it filled — is the general "appearance" signifier, and it
 * stays put as the cycle advances. `aria-label` is the stable action name the
 * kit test pins; `title` names the next stop.
 */
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
      <svg
        viewBox="0 0 24 24"
        width="17"
        height="17"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        aria-hidden="true"
        focusable="false"
      >
        {/* Ring + filled right half: the contrast/appearance glyph. */}
        <circle cx="12" cy="12" r="8.4" />
        <path d="M12 3.6a8.4 8.4 0 0 1 0 16.8z" fill="currentColor" stroke="none" />
      </svg>
    </IconButton>
  );
}
