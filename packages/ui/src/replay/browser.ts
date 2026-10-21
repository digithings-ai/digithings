/**
 * Download the active thread as one HTML file. Styles and same-origin images
 * come from the live page. The rest of the page (other threads, the memory
 * sidebar) is not included.
 */

import { downloadTextFile } from "../components/chat/transcript";
import { setExportKeepMounted } from "./export-mount";
import { snapshotFilename } from "./filename";
import {
  deploymentText,
  messageAnchor,
  omitScrollLockCss,
  questionText,
  serializeSnapshot,
  snapshotSource,
  transformSnapshotDom,
} from "./snapshot";

// Bounded runs keep this linear on page CSS (CodeQL js/polynomial-redos). The
// value cannot start or end with whitespace, so the \s runs never compete with it.
const URL_RE =
  /url\([ \t\n]{0,16}(['"]?)([^'"()\s](?:[^'"()]{0,4094}[^'"()\s])?)\1[ \t\n]{0,16}\)/g;

/** One slow asset must not hang the export; it is dropped instead. */
const ASSET_TIMEOUT_MS = 8000;

function fetchAsset(fetchImpl: typeof fetch, url: string): Promise<Response> {
  const signal =
    typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"
      ? AbortSignal.timeout(ASSET_TIMEOUT_MS)
      : undefined;
  return fetchImpl(url, signal ? { signal } : undefined);
}

export function liveSheetText(
  doc: Document | null = typeof document === "undefined" ? null : document,
): string {
  if (!doc) return "";
  const chunks: string[] = [];
  for (const sheet of Array.from(doc.styleSheets)) {
    try {
      for (const rule of Array.from(sheet.cssRules)) {
        const text = omitScrollLockCss(rule.cssText);
        if (text.trim()) chunks.push(text);
      }
    } catch {
      /* A cross-origin sheet cannot be read. Those rules are dropped. */
    }
  }
  return chunks.join("\n");
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
      const res = await fetchAsset(fetchImpl, absolute);
      if (!res.ok) {
        replacements.set(raw, "");
        continue;
      }
      const bytes = new Uint8Array(await res.arrayBuffer());
      const mime = (res.headers.get("content-type") || mimeOf(absolute)).split(";")[0].trim();
      if (!isSavableAsset(mime)) {
        replacements.set(raw, "");
        continue;
      }
      const encoded = bytesToBase64(bytes);
      replacements.set(raw, `data:${mime || "application/octet-stream"};base64,${encoded}`);
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

export async function inlineDomAssets(
  root: ParentNode,
  options: {
    origin?: string;
    href?: string;
    fetchImpl?: typeof fetch;
  } = {},
): Promise<void> {
  const origin = options.origin ?? (typeof location === "undefined" ? "" : location.origin);
  const href = options.href ?? (typeof location === "undefined" ? "" : location.href);
  const fetchImpl = options.fetchImpl ?? fetch;
  const nodes = [...root.querySelectorAll<HTMLElement>("img, image, use, source, video")];
  for (const node of nodes) {
    node.removeAttribute("srcset");
    for (const attr of ["src", "href", "poster"] as const) {
      const raw = node.getAttribute(attr);
      if (!raw || raw.startsWith("data:") || raw.startsWith("#")) continue;
      const absolute = origin ? sameOriginUrl(raw, origin, href) : null;
      if (!absolute) {
        node.removeAttribute(attr);
        continue;
      }
      try {
        const res = await fetchAsset(fetchImpl, absolute);
        if (!res.ok) {
          node.removeAttribute(attr);
          continue;
        }
        const bytes = new Uint8Array(await res.arrayBuffer());
        const mime = (res.headers.get("content-type") || mimeOf(absolute)).split(";")[0].trim();
        if (!isSavableAsset(mime)) {
          node.removeAttribute(attr);
          continue;
        }
        node.setAttribute(
          attr,
          `data:${mime || "application/octet-stream"};base64,${bytesToBase64(bytes)}`,
        );
      } catch {
        node.removeAttribute(attr);
      }
    }
  }
  if (!origin) return;
  for (const el of root.querySelectorAll<HTMLElement>("[style]")) {
    const style = el.getAttribute("style");
    if (!style || !style.includes("url(")) continue;
    el.setAttribute("style", await inlineAssetUrls(style, { origin, href, fetchImpl }));
  }
}

export const MISSING_THREAD_MESSAGE = "No open thread to export.";
export const MISSING_MESSAGE_MESSAGE = "Couldn't find that message to export.";

/** A failure the open page can show. The same slot is updated, not stacked. */
export function showSnapshotError(doc: Document, message: string): void {
  const host = doc.body ?? doc.documentElement;
  if (!host) return;
  let banner = host.querySelector<HTMLElement>("[data-slot='snapshot-export-error']");
  if (!banner) {
    banner = doc.createElement("div");
    banner.setAttribute("role", "alert");
    banner.setAttribute("data-slot", "snapshot-export-error");
    host.prepend(banner);
  }
  banner.textContent = message;
}

async function saveSnapshot(doc: Document, shell: HTMLElement, exportedAt: string): Promise<void> {
  const question = questionText(shell);
  const css = await inlineAssetUrls(liveSheetText(doc));
  transformSnapshotDom(shell);
  await inlineDomAssets(shell);
  const html = serializeSnapshot(shell, css);
  const name = snapshotFilename(deploymentText(doc), exportedAt, question);
  downloadTextFile(name, html, "text/html;charset=utf-8");
}

export async function downloadThreadSnapshot(
  doc: Document | null = typeof document === "undefined" ? null : document,
  exportedAt = new Date().toISOString(),
  anchor?: HTMLElement | null,
): Promise<void> {
  if (!doc?.documentElement) throw new Error(MISSING_THREAD_MESSAGE);
  // Closed reasoning and tool panels unmount on the live page. Mount them
  // only for this read, then put the page back.
  setExportKeepMounted(true);
  try {
    const shell = snapshotSource(doc, anchor);
    if (!shell) {
      const message = anchor ? MISSING_MESSAGE_MESSAGE : MISSING_THREAD_MESSAGE;
      showSnapshotError(doc, message);
      throw new Error(message);
    }
    await saveSnapshot(doc, shell, exportedAt);
  } finally {
    setExportKeepMounted(false);
  }
}

/**
 * The message-menu export. `trigger` is the menu button inside that
 * assistant message. A miss shows an error and does not save the thread.
 */
export async function downloadMessageSnapshot(
  doc: Document | null = typeof document === "undefined" ? null : document,
  exportedAt = new Date().toISOString(),
  messageId = "",
  trigger: HTMLElement | null = null,
): Promise<void> {
  if (!doc?.documentElement) throw new Error(MISSING_THREAD_MESSAGE);
  setExportKeepMounted(true);
  try {
    const anchor = messageAnchor(trigger, messageId);
    if (!anchor?.isConnected) {
      showSnapshotError(doc, MISSING_MESSAGE_MESSAGE);
      throw new Error(MISSING_MESSAGE_MESSAGE);
    }
    const shell = snapshotSource(doc, anchor);
    if (!shell) {
      showSnapshotError(doc, MISSING_MESSAGE_MESSAGE);
      throw new Error(MISSING_MESSAGE_MESSAGE);
    }
    await saveSnapshot(doc, shell, exportedAt);
  } finally {
    setExportKeepMounted(false);
  }
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

/** JSON and HTML bodies are not assets. Only images and fonts are inlined. */
function isSavableAsset(mime: string): boolean {
  const type = mime.toLowerCase();
  return (
    type.startsWith("image/") ||
    type.startsWith("font/") ||
    type === "application/font-woff" ||
    type === "application/font-woff2" ||
    type === "application/x-font-woff"
  );
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
