/**
 * Parent → embed page context for the popup widget (#3421 / #3581 / #3602).
 *
 * The launcher may post visible-page text, optional sanitized HTML, and an
 * optional screenshot data URL after `digichat:ready`. Only the immediate parent
 * browsing context may send this — never invent content behind auth the host
 * page did not already show.
 *
 * HTML is structurally allowlisted (DOM walk, `page-context-sanitize.ts`) on
 * both sender and receiver. Screenshot/vision multimodal remains deferred —
 * screenshot is acknowledged in the prompt text only, never inlined as base64
 * image parts.
 */

import {
  DEFAULT_PAGE_CONTEXT_HTML_CHARS,
  DEFAULT_PAGE_CONTEXT_TEXT_CHARS,
  PAGE_CONTEXT_PRIVATE_ATTR,
  sanitizePageHtml,
} from "./page-context-sanitize";

export const PAGE_CONTEXT_MESSAGE_TYPE = "digichat:page-context" as const;

export const MAX_PAGE_CONTEXT_TEXT_CHARS = DEFAULT_PAGE_CONTEXT_TEXT_CHARS;
/** Keep in sync with dashboard `PAGE_CONTEXT_HTML_MAX_CHARS`. */
export const MAX_PAGE_CONTEXT_HTML_CHARS = DEFAULT_PAGE_CONTEXT_HTML_CHARS;
export const MAX_PAGE_CONTEXT_SCREENSHOT_CHARS = 400_000;
export const MAX_PAGE_CONTEXT_AGE_MS = 5 * 60 * 1000;
export { sanitizePageHtml, PAGE_CONTEXT_PRIVATE_ATTR };
export type PageContextMessage = {
  type: typeof PAGE_CONTEXT_MESSAGE_TYPE;
  text: string;
  /** Optional sanitized HTML snapshot of the visible page (preferred over text). */
  html?: string;
  /** Optional `data:image/...;base64,...` from a same-document capture attempt. */
  screenshotDataUrl?: string;
  ts: number;
};

export function buildPageContextMessage(
  text: string,
  opts: {
    html?: string;
    screenshotDataUrl?: string;
    ts?: number;
    maxChars?: number;
    maxHtmlChars?: number;
  } = {},
): PageContextMessage {
  const max = opts.maxChars ?? MAX_PAGE_CONTEXT_TEXT_CHARS;
  const clipped = text.replace(/\s+/g, " ").trim().slice(0, max);
  const htmlRaw = opts.html?.trim();
  const html = htmlRaw
    ? sanitizePageHtml(htmlRaw, opts.maxHtmlChars ?? MAX_PAGE_CONTEXT_HTML_CHARS)
    : undefined;
  const shot = opts.screenshotDataUrl?.trim();
  return {
    type: PAGE_CONTEXT_MESSAGE_TYPE,
    text: clipped,
    html: html || undefined,
    screenshotDataUrl:
      shot &&
      shot.startsWith("data:image/png") &&
      shot.length <= MAX_PAGE_CONTEXT_SCREENSHOT_CHARS
        ? shot
        : undefined,
    ts: opts.ts ?? Date.now(),
  };
}

/**
 * Accept page-context only from the resolved parent origin (immediate iframe parent).
 * Unlike seed/theme, third-party registered hosts may send this — they describe
 * their own already-visible DOM.
 */
export function parsePageContextMessage(
  event: MessageEvent,
  parentOrigin: string | null,
): PageContextMessage | null {
  if (!parentOrigin || event.origin !== parentOrigin) return null;
  const data = event.data as Record<string, unknown> | null;
  if (!data || data.type !== PAGE_CONTEXT_MESSAGE_TYPE) return null;
  if (typeof data.ts !== "number" || Date.now() - data.ts > MAX_PAGE_CONTEXT_AGE_MS) {
    return null;
  }
  if (typeof data.text !== "string") return null;
  if (data.text.length > MAX_PAGE_CONTEXT_TEXT_CHARS) return null;
  let html: string | undefined;
  if (data.html !== undefined) {
    if (typeof data.html !== "string") return null;
    if (data.html.length > MAX_PAGE_CONTEXT_HTML_CHARS) return null;
    html = sanitizePageHtml(data.html);
  }
  let screenshotDataUrl: string | undefined;
  if (data.screenshotDataUrl !== undefined) {
    if (typeof data.screenshotDataUrl !== "string") return null;
    // Widget emits PNG data URLs only — reject svg+xml / other image/* to
    // avoid storing scriptable payloads even though we never inline into the model.
    if (
      !data.screenshotDataUrl.startsWith("data:image/png") ||
      data.screenshotDataUrl.length > MAX_PAGE_CONTEXT_SCREENSHOT_CHARS
    ) {
      return null;
    }
    screenshotDataUrl = data.screenshotDataUrl;
  }
  return {
    type: PAGE_CONTEXT_MESSAGE_TYPE,
    text: data.text,
    html: html || undefined,
    screenshotDataUrl,
    ts: data.ts,
  };
}

/** Visible-page text only — no hidden inputs, no off-DOM scrapes. */
export function extractVisiblePageText(
  doc: { body?: { innerText?: string } | null },
  maxChars: number = MAX_PAGE_CONTEXT_TEXT_CHARS,
): string {
  const raw = doc.body?.innerText ?? "";
  return raw.replace(/\s+/g, " ").trim().slice(0, maxChars);
}

/**
 * Format page context for the next user turn. HTML is preferred for structure;
 * plain text is a fallback / supplement. Screenshot is acknowledged but not
 * inlined as base64 into the chat prompt (vision multimodal deferred).
 */
export function formatPageContextForPrompt(ctx: {
  text: string;
  html?: string;
  screenshotDataUrl?: string;
}): string {
  const text = ctx.text.trim();
  const html = ctx.html?.trim() ?? "";
  if (!text && !html && !ctx.screenshotDataUrl) return "";
  const lines = [
    "[Page context from the host page — content already visible to the visitor.]",
  ];
  if (html) {
    lines.push("[Page HTML snapshot — structure and labels on the visible page:]");
    lines.push(html);
  }
  if (text) {
    if (html) lines.push("[Visible text (supplement):]");
    lines.push(text);
  }
  if (ctx.screenshotDataUrl) {
    lines.push(
      "[A screenshot of the visible viewport was attached by the host widget — vision multimodal is not enabled; use the HTML/text above.]",
    );
  }
  return lines.join("\n");
}