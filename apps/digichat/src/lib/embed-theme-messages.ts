/**
 * Parent ↔ embed theme sync for first-party digichat iframes.
 *
 * digithings.ai (and other allowed parents) post `{ type: "digichat:theme", theme }`
 * so the embed can follow the parent site's light/dark mode without inventing a
 * parallel token system — the embed still flips canon `[data-theme]` / `.dark`|
 * `.light`, the same surface ThemeClassSync and tenant pins already use.
 * An optional `palette` rides the same message. Mode stays pinned for a tenant;
 * the palette is how a first-party parent shares `dt-palette` into the iframe.
 *
 * Initial paint uses optional `?theme=light|dark` on the iframe URL (set by the
 * parent after reading `document.documentElement[data-theme]`). Live toggles
 * use postMessage so the iframe does not reload.
 */

import { isPaletteId } from "@digithings/ui/theme";

export const THEME_MESSAGE_TYPE = "digichat:theme" as const;

export type EmbedTheme = "light" | "dark";

export type ThemeMessage = {
  type: typeof THEME_MESSAGE_TYPE;
  theme: EmbedTheme;
  ts: number;
  /** `default` or absent clears `data-palette`. A palette id sets it. */
  palette?: string;
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
  palette?: string,
): ThemeMessage {
  const message: ThemeMessage = { type: THEME_MESSAGE_TYPE, theme, ts };
  if (palette) message.palette = palette;
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
  return palette
    ? { type: THEME_MESSAGE_TYPE, theme, ts: data.ts, palette }
    : { type: THEME_MESSAGE_TYPE, theme, ts: data.ts };
}

function parseEmbedPalette(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const id = value.trim().toLowerCase();
  if (id === "default") return "default";
  return isPaletteId(id) ? id : undefined;
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

/** `default` and an absent id clear the attribute. A known id paints it. */
export function applyEmbedDocumentPalette(
  palette: string | undefined,
  el: {
    setAttribute(name: string, value: string): void;
    removeAttribute(name: string): void;
  } = document.documentElement,
): void {
  if (!palette || palette === "default") el.removeAttribute("data-palette");
  else el.setAttribute("data-palette", palette);
}
