/**
 * Parent ↔ embed theme sync for first-party digichat iframes.
 *
 * digithings.ai (and other allowed parents) post `{ type: "digichat:theme", theme }`
 * so the embed can follow the parent site's light/dark mode without inventing a
 * parallel token system — the embed still flips canon `[data-theme]` / `.dark`|
 * `.light`, the same surface ThemeClassSync and tenant pins already use.
 *
 * Initial paint uses optional `?theme=light|dark` on the iframe URL (set by the
 * parent after reading `document.documentElement[data-theme]`). Live toggles
 * use postMessage so the iframe does not reload.
 */

import { normalizePalette, type PaletteName } from "@digithings/ui/theme";

export const THEME_MESSAGE_TYPE = "digichat:theme" as const;

export type EmbedTheme = "light" | "dark";

export type ThemeMessage = {
  type: typeof THEME_MESSAGE_TYPE;
  theme: EmbedTheme;
  ts: number;
};

/** Max age for a theme postMessage (ignore stale queued events). */
export const MAX_THEME_AGE_MS = 5 * 60 * 1000;

export function parseEmbedThemeParam(
  raw: string | null | undefined,
): EmbedTheme | null {
  if (raw === "light" || raw === "dark") return raw;
  return null;
}

export function buildThemeMessage(theme: EmbedTheme, ts = Date.now()): ThemeMessage {
  return { type: THEME_MESSAGE_TYPE, theme, ts };
}

export function parseThemeMessage(
  event: MessageEvent,
  allowedParentOrigins: ReadonlySet<string>,
): ThemeMessage | null {
  if (!allowedParentOrigins.has(event.origin)) return null;
  const data = event.data as Record<string, unknown> | null;
  if (!data || data.type !== THEME_MESSAGE_TYPE) return null;
  const theme = parseEmbedThemeParam(
    typeof data.theme === "string" ? data.theme : null,
  );
  if (!theme) return null;
  if (typeof data.ts !== "number") return null;
  if (Date.now() - data.ts > MAX_THEME_AGE_MS) return null;
  return { type: THEME_MESSAGE_TYPE, theme, ts: data.ts };
}

/** Apply canon theme attributes used by tokens.css + Tailwind `dark:`. */
export function applyEmbedDocumentTheme(
  theme: EmbedTheme,
  el: {
    setAttribute(name: string, value: string): void;
    classList: { add(...tokens: string[]): void; remove(...tokens: string[]): void };
  } = document.documentElement,
): void {
  el.setAttribute("data-theme", theme);
  el.classList.add(theme === "light" ? "light" : "dark");
  el.classList.remove(theme === "light" ? "dark" : "light");
}

/**
 * A visitor's own `/theme` pick on a tenant embed (2.6.6). The chat starts on
 * the tenant's configured theme; a pick lasts for this tab only
 * (sessionStorage, keyed by embed host so two tenants on one origin never
 * share it) and is never written to the platform `dt-theme` / `dt-palette`
 * localStorage keys.
 */
export type EmbedUserTheme = { mode: EmbedTheme; palette: PaletteName };

/** Fired on window after a pick is written, so the embed re-reads it. */
export const EMBED_USER_THEME_EVENT = "dc-embed-theme-change";

export function embedUserThemeKey(host: string | null | undefined): string {
  return `dc-embed-theme:${host?.trim() || "default"}`;
}

type SessionStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function sessionStore(): SessionStore | null {
  try {
    return typeof sessionStorage === "undefined" ? null : sessionStorage;
  } catch {
    return null;
  }
}

/** The stored pick as written (a stable string, for useSyncExternalStore). */
export function readEmbedUserThemeRaw(
  key: string,
  store: SessionStore | null = sessionStore(),
): string | null {
  try {
    return store?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function parseEmbedUserTheme(raw: string | null): EmbedUserTheme | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { mode?: unknown; palette?: unknown };
    const mode = parseEmbedThemeParam(typeof parsed.mode === "string" ? parsed.mode : null);
    if (!mode) return null;
    return {
      mode,
      palette: normalizePalette(typeof parsed.palette === "string" ? parsed.palette : null),
    };
  } catch {
    return null;
  }
}

export function readEmbedUserTheme(
  key: string,
  store: SessionStore | null = sessionStore(),
): EmbedUserTheme | null {
  return parseEmbedUserTheme(readEmbedUserThemeRaw(key, store));
}

export function writeEmbedUserTheme(
  key: string,
  value: EmbedUserTheme | null,
  store: SessionStore | null = sessionStore(),
): void {
  try {
    if (store) {
      if (value) store.setItem(key, JSON.stringify(value));
      else store.removeItem(key);
    }
  } catch {
    /* private mode */
  }
  try {
    if (typeof window !== "undefined") window.dispatchEvent(new Event(EMBED_USER_THEME_EVENT));
  } catch {
    /* ignore */
  }
}

export function subscribeEmbedUserTheme(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(EMBED_USER_THEME_EVENT, onChange);
  return () => window.removeEventListener(EMBED_USER_THEME_EVENT, onChange);
}

/** Paint the pick's palette (the tenant default paints none). */
export function applyEmbedPalette(
  palette: PaletteName,
  el: {
    setAttribute(name: string, value: string): void;
    removeAttribute(name: string): void;
  } = document.documentElement,
): void {
  if (palette === "default") el.removeAttribute("data-palette");
  else el.setAttribute("data-palette", palette);
}
