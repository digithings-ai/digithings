/**
 * Download the open thread as one HTML file. Styles come from the live page
 * when they are the chat sheets (the closest match to the tab Chris is in),
 * and from the authenticated asset route otherwise.
 */

import { downloadTextFile } from "../components/chat/transcript";
import { readPaintedTheme, readThemeState } from "../theme";
import { messagesToReplay, type ReplayChromeInput } from "./from-messages";
import { buildReplayHtml, replayDownloadName } from "./html";
import { REPLAY_SHELL_CSS } from "./styles";
import type { ReplayAccent, ReplayView } from "./types";

export type BrowserReplayInput = {
  messages: readonly unknown[];
  deployment?: string;
  title?: string;
  welcome?: string;
  welcomeBody?: readonly string[];
  suggestions?: readonly string[];
  placeholder?: string;
  accent?: ReplayAccent | null;
  view?: ReplayView;
  /** App base path for the asset route; defaults to NEXT_PUBLIC_DIGICHAT_BASE_PATH. */
  basePath?: string;
};

const VIEWS = new Set<ReplayView>(["quiet", "balanced", "verbose"]);
const URL_RE = /url\(\s*(['"]?)([^'")]+)\1\s*\)/g;

export function cssLooksLikeChat(css: string): boolean {
  return css.includes(".aui-user-message-content") || css.includes(".aui-md");
}

export function liveSheetText(
  doc: Document | null = typeof document === "undefined" ? null : document,
): string {
  if (!doc) return "";
  const chunks: string[] = [];
  for (const sheet of Array.from(doc.styleSheets)) {
    try {
      for (const rule of Array.from(sheet.cssRules)) chunks.push(rule.cssText);
    } catch {
      /* A cross-origin sheet cannot be read. The asset route covers that case. */
    }
  }
  return chunks.join("\n");
}

export async function resolveReplayCss(
  liveCss: string,
  loadBundled: () => Promise<string>,
  inline: (css: string) => Promise<string> = inlineAssetUrls,
): Promise<string> {
  if (cssLooksLikeChat(liveCss)) return inline(liveCss);
  return loadBundled();
}

export async function inlineAssetUrls(
  css: string,
  options: {
    origin?: string;
    href?: string;
    fetchImpl?: typeof fetch;
  } = {},
): Promise<string> {
  const origin = options.origin ?? (typeof location === "undefined" ? "" : location.origin);
  const href = options.href ?? (typeof location === "undefined" ? "" : location.href);
  const fetchImpl = options.fetchImpl ?? fetch;
  URL_RE.lastIndex = 0;
  if (!origin || origin === "null") return css;
  const replacements = new Map<string, string>();
  for (const match of css.matchAll(URL_RE)) {
    const raw = match[2];
    if (!raw || raw.startsWith("data:") || raw.startsWith("#")) continue;
    if (replacements.has(raw)) continue;
    const absolute = sameOriginUrl(raw, origin, href);
    if (!absolute) {
      replacements.set(raw, "");
      continue;
    }
    try {
      const res = await fetchImpl(absolute);
      if (!res.ok) {
        replacements.set(raw, "");
        continue;
      }
      const bytes = new Uint8Array(await res.arrayBuffer());
      const mime = (res.headers.get("content-type") || mimeOf(absolute)).split(";")[0].trim();
      replacements.set(
        raw,
        `data:${mime || "application/octet-stream"};base64,${bytesToBase64(bytes)}`,
      );
    } catch {
      replacements.set(raw, "");
    }
  }
  return css.replace(URL_RE, (full, _quote: string, raw: string) => {
    if (!replacements.has(raw)) return full;
    const data = replacements.get(raw);
    return data ? `url("${data}")` : "none";
  });
}

export async function downloadThreadReplay(input: BrowserReplayInput): Promise<void> {
  const doc = messagesToReplay(input.messages, chromeFromBrowser(input), new Date().toISOString());
  const live = liveSheetText();
  // The asset route's bundle already ends with the replay shell CSS.
  const css = cssLooksLikeChat(live)
    ? `${await inlineAssetUrls(live)}\n${REPLAY_SHELL_CSS}`
    : await loadAssetRoute(replayAssetsUrl(input.basePath ?? publicBasePath()));
  const html = buildReplayHtml(doc, css);
  downloadTextFile(replayDownloadName(doc), html, "text/html;charset=utf-8");
}

/** `/api/replay-assets` under the app's base path (digithings.ai serves digichat at /chat). */
export function replayAssetsUrl(basePath: string | undefined): string {
  const base = (basePath ?? "").trim().replace(/\/+$/, "");
  return `${base}/api/replay-assets`;
}

function publicBasePath(): string {
  try {
    // Inlined by Next at build time, like the app's own base-path helper.
    return process.env.NEXT_PUBLIC_DIGICHAT_BASE_PATH ?? "";
  } catch {
    return "";
  }
}

async function loadAssetRoute(url: string): Promise<string> {
  const res = await fetch(url, { credentials: "same-origin" });
  if (!res.ok) throw new Error("replay assets unavailable");
  return res.text();
}

function chromeFromBrowser(input: BrowserReplayInput): ReplayChromeInput {
  const painted = readPaintedTheme();
  const stored = readThemeState();
  const deployment =
    input.deployment?.trim() ||
    (typeof document === "undefined"
      ? ""
      : document.querySelector("[data-deployment]")?.getAttribute("data-deployment") || "");
  return {
    deployment,
    title: input.title,
    welcome: input.welcome,
    welcomeBody: input.welcomeBody,
    suggestions: input.suggestions,
    placeholder: input.placeholder,
    accent: input.accent ?? readAccent(),
    theme: {
      preference: stored.preference,
      resolved: painted.resolved,
      palette: painted.palette,
      view: input.view ?? readView(),
    },
  };
}

function readView(): ReplayView {
  if (typeof document === "undefined") return "balanced";
  const raw = document.querySelector("[data-view]")?.getAttribute("data-view") ?? "";
  return VIEWS.has(raw as ReplayView) ? (raw as ReplayView) : "balanced";
}

function readAccent(): ReplayAccent | null {
  if (typeof document === "undefined") return null;
  const host = document.querySelector("[data-stock-product]");
  if (!host) return null;
  const style = getComputedStyle(host);
  const color = style.getPropertyValue("--accent").trim();
  const foreground = style.getPropertyValue("--accent-foreground").trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(color) || !/^#[0-9a-fA-F]{6}$/.test(foreground)) return null;
  return { color, foreground };
}

function sameOriginUrl(raw: string, origin: string, href: string): string | null {
  try {
    const url = new URL(raw, href || origin);
    if (url.origin !== origin) return null;
    return url.href;
  } catch {
    return null;
  }
}

function mimeOf(url: string): string {
  const path = url.split("?")[0]?.toLowerCase() ?? "";
  if (path.endsWith(".woff2")) return "font/woff2";
  if (path.endsWith(".woff")) return "font/woff";
  if (path.endsWith(".svg")) return "image/svg+xml";
  if (path.endsWith(".png")) return "image/png";
  if (path.endsWith(".css")) return "text/css";
  return "application/octet-stream";
}

function bytesToBase64(bytes: Uint8Array): string {
  if (typeof Buffer !== "undefined") return Buffer.from(bytes).toString("base64");
  let binary = "";
  const size = 0x8000;
  for (let i = 0; i < bytes.length; i += size) {
    binary += String.fromCharCode(...bytes.subarray(i, i + size));
  }
  return btoa(binary);
}
