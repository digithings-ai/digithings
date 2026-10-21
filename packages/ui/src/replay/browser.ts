/**
 * Download the open thread as one HTML file. Styles and same-origin images
 * come from the live page, so the file matches the tab it was saved from.
 */

import { downloadTextFile } from "../components/chat/transcript";
import { snapshotFilename } from "./filename";
import {
  deploymentText,
  questionText,
  serializeSnapshot,
  transformSnapshotDom,
} from "./snapshot";

const URL_RE = /url\(\s*(['"]?)([^'")]+)\1\s*\)/g;

export function liveSheetText(
  doc: Document | null = typeof document === "undefined" ? null : document,
): string {
  if (!doc) return "";
  const chunks: string[] = [];
  for (const sheet of Array.from(doc.styleSheets)) {
    try {
      for (const rule of Array.from(sheet.cssRules)) chunks.push(rule.cssText);
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
      const res = await fetchImpl(absolute);
      if (!res.ok) {
        replacements.set(raw, "");
        continue;
      }
      const bytes = new Uint8Array(await res.arrayBuffer());
      const mime = (res.headers.get("content-type") || mimeOf(absolute)).split(";")[0].trim();
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
  const nodes = [
    ...root.querySelectorAll<HTMLElement>("img, image, use, source, video"),
  ];
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
        const res = await fetchImpl(absolute);
        if (!res.ok) {
          node.removeAttribute(attr);
          continue;
        }
        const bytes = new Uint8Array(await res.arrayBuffer());
        const mime = (res.headers.get("content-type") || mimeOf(absolute)).split(";")[0].trim();
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

export async function downloadThreadSnapshot(
  doc: Document | null = typeof document === "undefined" ? null : document,
  exportedAt = new Date().toISOString(),
): Promise<void> {
  if (!doc?.documentElement) return;
  const css = await inlineAssetUrls(liveSheetText(doc));
  const clone = doc.documentElement.cloneNode(true) as HTMLElement;
  transformSnapshotDom(clone);
  await inlineDomAssets(clone);
  const html = serializeSnapshot(clone, css);
  const name = snapshotFilename(deploymentText(doc), exportedAt, questionText(doc));
  downloadTextFile(name, html, "text/html;charset=utf-8");
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
