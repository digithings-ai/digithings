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
 *
 * A first-party parent also shares its `[data-palette]` on the same message.
 * The palette never paints the document on its own: `resolveEmbedPalette`
 * folds it into the one palette channel the embed already owns (visitor
 * pick > parent > default), so `data-palette` keeps a single writer.
 */

import type { EmbedChatPrefsApi } from "@digithings/ui/chat/stock";
import { normalizePalette, themeColorFor, type PaletteName } from "@digithings/ui/theme";

export const THEME_MESSAGE_TYPE = "digichat:theme" as const;

export type EmbedTheme = "light" | "dark";

export type ThemeMessage = {
  type: typeof THEME_MESSAGE_TYPE;
  theme: EmbedTheme;
  ts: number;
  /** A known palette id. Absent means the parent has no palette to share. */
  palette?: PaletteName;
};

/** Max age for a theme postMessage (ignore stale queued events). */
export const MAX_THEME_AGE_MS = 5 * 60 * 1000;

export function parseEmbedThemeParam(
  raw: string | null | undefined,
): EmbedTheme | null {
  if (raw === "light" || raw === "dark") return raw;
  return null;
}

export function buildThemeMessage(
  theme: EmbedTheme,
  ts = Date.now(),
  palette?: PaletteName,
): ThemeMessage {
  const message: ThemeMessage = { type: THEME_MESSAGE_TYPE, theme, ts };
  if (palette && palette !== "default") message.palette = palette;
  return message;
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
  const palette = parseEmbedPalette(data.palette);
  // An unknown or default palette costs the palette only, never the theme.
  return palette
    ? { type: THEME_MESSAGE_TYPE, theme, ts: data.ts, palette }
    : { type: THEME_MESSAGE_TYPE, theme, ts: data.ts };
}

function parseEmbedPalette(value: unknown): PaletteName | undefined {
  if (typeof value !== "string") return undefined;
  const palette = normalizePalette(value.trim().toLowerCase());
  return palette === "default" ? undefined : palette;
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
 * (sessionStorage, keyed by the resolved tenant slug so two tenants on one
 * origin never share it) and is never written to the platform `dt-theme` /
 * `dt-palette` localStorage keys.
 */
export type EmbedUserTheme = { mode: EmbedTheme; palette: PaletteName };

/** Fired on window after a pick is written, so the embed re-reads it. */
export const EMBED_USER_THEME_EVENT = "dc-embed-theme-change";

/** Storage key for one tenant's pick: the resolved tenant slug, not the raw `?host=`. */
export function embedUserThemeKey(tenantSlug: string): string {
  return `dc-embed-theme:${tenantSlug}`;
}

type SessionStore = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/** Used when sessionStorage is blocked, so a pick still lasts for this page. */
const memoryStore: SessionStore = (() => {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
  };
})();

/** One write probe per sessionStorage object; a later failed write also flips it. */
let probed: { store: SessionStore; writable: boolean } | null = null;

function sessionStore(): SessionStore | null {
  let session: SessionStore;
  try {
    if (typeof sessionStorage === "undefined") {
      return typeof window === "undefined" ? null : memoryStore;
    }
    session = sessionStorage;
  } catch {
    return memoryStore;
  }
  if (probed?.store !== session) {
    // Safari private mode and a full quota expose sessionStorage but throw on write.
    let writable = true;
    try {
      // Not a pick key: embedUserThemeKey always has a ":" before the slug.
      session.setItem("dc-embed-theme-probe", "1");
      session.removeItem("dc-embed-theme-probe");
    } catch {
      writable = false;
    }
    probed = { store: session, writable };
  }
  return probed.writable ? session : memoryStore;
}

/**
 * What a `/theme` pick means on an embed. `auto` drops the pick, so the chat
 * goes back to the parent / `?theme=` / tenant theme; a mode keeps the palette.
 */
export function embedThemePick(
  preference: "light" | "dark" | "auto",
  palette: PaletteName,
): EmbedUserTheme | null {
  return preference === "auto" ? null : { mode: preference, palette };
}

/**
 * The `/theme` part of an embed's prefs api. The embed owns its theme, so
 * reads come from what it paints and a pick goes to `onThemePick` (this tab
 * only), never to the platform's dt-theme / dt-palette keys.
 */
export function embedThemePrefs(opts: {
  theme: EmbedUserTheme;
  onThemePick: (next: EmbedUserTheme | null) => void;
  openTheme: () => void;
}): Pick<EmbedChatPrefsApi, "openTheme" | "themeState" | "setTheme"> {
  return {
    openTheme: opts.openTheme,
    themeState: {
      preference: opts.theme.mode,
      palette: opts.theme.palette,
      resolved: opts.theme.mode,
    },
    setTheme: (preference, palette) => {
      opts.onThemePick(embedThemePick(preference, palette));
    },
  };
}

/** The mode an embed paints: pick > parent postMessage > `?theme=` > tenant (default dark). */
export function resolveEmbedTheme(sources: {
  pick: EmbedUserTheme | null;
  parent: EmbedTheme | null;
  url: EmbedTheme | null;
  tenant: string | null | undefined;
}): EmbedTheme {
  return (
    sources.pick?.mode ?? sources.parent ?? sources.url ?? (sources.tenant === "light" ? "light" : "dark")
  );
}

/**
 * The palette an embed paints: a visitor `/theme` pick > the parent's
 * `digichat:theme` palette > the default look. The embed's existing theme
 * effect is the only writer of `data-palette`.
 */
export function resolveEmbedPalette(sources: {
  pick: EmbedUserTheme | null;
  parent: PaletteName | null;
}): PaletteName {
  return sources.pick?.palette ?? sources.parent ?? "default";
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

function putPick(store: SessionStore, key: string, value: EmbedUserTheme | null): void {
  if (value) store.setItem(key, JSON.stringify(value));
  else store.removeItem(key);
}

export function writeEmbedUserTheme(
  key: string,
  value: EmbedUserTheme | null,
  store: SessionStore | null = sessionStore(),
): void {
  try {
    if (store) putPick(store, key, value);
  } catch {
    // The write failed after the probe passed (quota, private mode): keep the
    // pick for this page in memory and read from there from now on.
    if (probed?.store === store) {
      probed = { store, writable: false };
      try {
        putPick(memoryStore, key, value);
      } catch {
        /* unreachable */
      }
    }
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

/** Embed canvas per mode; matches the pin script in embed-route-shell.tsx. */
const EMBED_CANVAS: Record<EmbedTheme, string> = {
  light: "#f1f0eb", // canon-allow: browser theme-color meta for the embed canvas, same pair as embed-route-shell.tsx
  dark: "#121417", // canon-allow: browser theme-color meta for the embed canvas, same pair as embed-route-shell.tsx
};

/** The browser `theme-color` for an embed mode and palette. */
export function embedThemeColor(mode: EmbedTheme, palette: PaletteName): string {
  return palette === "default" ? EMBED_CANVAS[mode] : themeColorFor(palette, mode);
}

/** Paint the pick's palette (the tenant default paints none) and keep `theme-color` in step. */
export function applyEmbedPalette(
  palette: PaletteName,
  mode: EmbedTheme,
  doc: Document = document,
): void {
  const el = doc.documentElement;
  if (palette === "default") el.removeAttribute("data-palette");
  else el.setAttribute("data-palette", palette);
  try {
    doc.querySelector('meta[name="theme-color"]')?.setAttribute("content", embedThemeColor(mode, palette));
  } catch {
    /* ignore */
  }
}
