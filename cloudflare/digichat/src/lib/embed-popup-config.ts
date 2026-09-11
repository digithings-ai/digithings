/**
 * Popup widget embed (#3421) — pure config + URL builder for the launcher script.
 *
 * Host pages load `/widget.js` (or a pinned digichat origin) and pass options via
 * `data-*` attributes on the script tag. The launcher opens a bottom-right panel
 * that iframes `/embed?layout=embed` against the same tenant registry as full-page.
 */

export type PopupLauncherMode = "dot" | "bar";

export type PopupWidgetConfig = {
  /** digichat origin that serves /embed and /widget.js (no trailing slash). */
  origin: string;
  /** Registry host key (`?host=`), e.g. digithings.ai or occ.digithings.ai. */
  host: string;
  /** Optional tenant embed token (`?token=`). */
  token?: string;
  mode: PopupLauncherMode;
  theme?: "light" | "dark";
  accent?: string;
  /** When true, parent sends visible-page text (+ optional screenshot) after ready. */
  pageContext: boolean;
  /** Max chars of visible text included in digichat:page-context. */
  pageContextMaxChars: number;
};

export const DEFAULT_POPUP_PAGE_CONTEXT_MAX_CHARS = 8_000;

const HEX = /^#[0-9a-fA-F]{6}$/;

function firstAttr(
  el: { getAttribute(name: string): string | null },
  names: readonly string[],
): string | undefined {
  for (const name of names) {
    const v = el.getAttribute(name)?.trim();
    if (v) return v;
  }
  return undefined;
}

/** Resolve digichat origin from an absolute script URL, or empty if not absolute. */
export function originFromScriptSrc(scriptSrc: string): string {
  try {
    const u = new URL(scriptSrc);
    if (u.protocol !== "http:" && u.protocol !== "https:") return "";
    return u.origin;
  } catch {
    return "";
  }
}

export function parsePopupLauncherMode(raw: string | undefined | null): PopupLauncherMode {
  return raw?.trim().toLowerCase() === "bar" ? "bar" : "dot";
}

/**
 * Read launcher options from the active `<script src="…/widget.js">` element.
 * Missing `data-origin` falls back to the script's own origin (same-host deploy).
 */
export function readPopupWidgetConfigFromScript(
  script: { getAttribute(name: string): string | null; src?: string },
  defaults: { origin?: string; host?: string } = {},
): PopupWidgetConfig | null {
  const src = (script.src ?? script.getAttribute("src") ?? "").trim();
  const fromSrc = src ? originFromScriptSrc(src) : "";
  const origin = (
    firstAttr(script, ["data-origin", "data-digichat-origin"]) ??
    defaults.origin ??
    fromSrc
  )
    .trim()
    .replace(/\/$/, "");
  const host = (
    firstAttr(script, ["data-host", "data-embed-host"]) ??
    defaults.host ??
    ""
  ).trim();
  if (!origin || !host) return null;

  const token = firstAttr(script, ["data-token", "data-embed-token"]);
  const themeRaw = firstAttr(script, ["data-theme"])?.toLowerCase();
  const theme = themeRaw === "light" || themeRaw === "dark" ? themeRaw : undefined;
  const accentRaw = firstAttr(script, ["data-accent"]);
  const accent = accentRaw && HEX.test(accentRaw) ? accentRaw : undefined;
  const pageContextAttr = firstAttr(script, ["data-page-context", "data-pagecontext"]);
  const pageContext =
    pageContextAttr === "1" || pageContextAttr?.toLowerCase() === "true";
  const maxRaw = firstAttr(script, ["data-page-context-max-chars"]);
  const maxParsed = maxRaw ? Number.parseInt(maxRaw, 10) : NaN;
  // Must stay ≤ MAX_PAGE_CONTEXT_TEXT_CHARS in embed-page-context-messages.ts
  // or the embed silently rejects the postMessage.
  const pageContextMaxChars =
    Number.isFinite(maxParsed) && maxParsed > 0
      ? Math.min(maxParsed, DEFAULT_POPUP_PAGE_CONTEXT_MAX_CHARS)
      : DEFAULT_POPUP_PAGE_CONTEXT_MAX_CHARS;

  return {
    origin,
    host,
    token,
    mode: parsePopupLauncherMode(firstAttr(script, ["data-mode", "data-launcher"])),
    theme,
    accent,
    pageContext,
    pageContextMaxChars,
  };
}

/** Build the iframe URL for the popup panel (`layout=embed`, not full-page wide). */
export function buildPopupEmbedSrc(cfg: PopupWidgetConfig): string {
  const url = new URL(`${cfg.origin.replace(/\/$/, "")}/embed`);
  url.searchParams.set("host", cfg.host);
  url.searchParams.set("layout", "embed");
  if (cfg.token) url.searchParams.set("token", cfg.token);
  if (cfg.theme) url.searchParams.set("theme", cfg.theme);
  if (cfg.accent) url.searchParams.set("accent", cfg.accent);
  return url.toString();
}
