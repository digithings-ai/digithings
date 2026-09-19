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

/** Filename for the system document chip on the user message. */
export const PAGE_CONTEXT_ATTACHMENT_NAME = "page-context.html";

export type PageContextFileUiPart = {
  type: "file";
  filename: string;
  mediaType: string;
  url: string;
};

/** Composer `CreateAttachment` shape — file part so the chip is not inlined as text. */
export type PageContextCreateAttachment = {
  name: string;
  type: "document";
  contentType: string;
  content: Array<{
    type: "file";
    filename: string;
    data: string;
    mimeType: string;
  }>;
};

export function isPageContextAttachmentName(name: string | undefined): boolean {
  return name === PAGE_CONTEXT_ATTACHMENT_NAME;
}

export function isPageContextFilePart(part: {
  type?: string;
  filename?: string;
}): boolean {
  return part.type === "file" && isPageContextAttachmentName(part.filename);
}

/** Marker folded into the document body so BFF expansion can acknowledge a screenshot. */
const PAGE_CONTEXT_SCREENSHOT_MARKER = "<!-- digichat:page-context-screenshot -->";

function htmlCommentSafe(text: string): string {
  return text.replace(/--+/g, "—");
}

function visibleTextComment(text: string): string {
  return `<!-- digichat:page-context-text\n${htmlCommentSafe(text)}\n-->`;
}

/** Snapshot stored on the document chip — HTML preferred, visible text as fallback. */
export function pageContextSnapshotBody(ctx: {
  text: string;
  html?: string;
  screenshotDataUrl?: string;
}): { body: string; mediaType: string } {
  const html = ctx.html?.trim() ?? "";
  const text = ctx.text.trim();
  const extras: string[] = [];
  if (html && text) extras.push(visibleTextComment(text));
  if (ctx.screenshotDataUrl) extras.push(PAGE_CONTEXT_SCREENSHOT_MARKER);
  const suffix = extras.length ? `\n${extras.join("\n")}` : "";
  if (html) return { body: html + suffix, mediaType: "text/html" };
  return { body: text + suffix, mediaType: "text/plain" };
}

export function encodeTextDataUrl(mediaType: string, body: string): string {
  return `data:${mediaType};charset=utf-8,${encodeURIComponent(body)}`;
}

export function decodeDataUrlText(url: string): string {
  if (!url.startsWith("data:")) return url;
  const comma = url.indexOf(",");
  if (comma < 0) return "";
  const header = url.slice(5, comma);
  const payload = url.slice(comma + 1);
  if (header.includes(";base64")) {
    try {
      if (typeof Buffer !== "undefined") {
        return Buffer.from(payload, "base64").toString("utf8");
      }
      const binary = atob(payload);
      const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
      return new TextDecoder().decode(bytes);
    } catch {
      return payload;
    }
  }
  try {
    return decodeURIComponent(payload);
  } catch {
    return payload;
  }
}

export function pageContextFileUiPart(
  ctx: { text: string; html?: string; screenshotDataUrl?: string } | null | undefined,
): PageContextFileUiPart | null {
  if (!ctx) return null;
  const { body, mediaType } = pageContextSnapshotBody(ctx);
  if (!body) return null;
  return {
    type: "file",
    filename: PAGE_CONTEXT_ATTACHMENT_NAME,
    mediaType,
    url: encodeTextDataUrl(mediaType, body),
  };
}

export function pageContextCreateAttachment(
  ctx: { text: string; html?: string; screenshotDataUrl?: string } | null | undefined,
): PageContextCreateAttachment | null {
  const file = pageContextFileUiPart(ctx);
  if (!file) return null;
  return {
    name: file.filename,
    type: "document",
    contentType: file.mediaType,
    content: [
      {
        type: "file",
        filename: file.filename,
        data: file.url,
        mimeType: file.mediaType,
      },
    ],
  };
}

/**
 * User-visible parts: the question text plus a document file part for the chip.
 * Do not prefix the question — BFF expansion feeds digigraph.
 */
export function shapeUserMessageParts(
  question: string,
  ctx: { text: string; html?: string; screenshotDataUrl?: string } | null | undefined,
): Array<{ type: "text"; text: string } | PageContextFileUiPart> {
  const text = question.trim();
  const parts: Array<{ type: "text"; text: string } | PageContextFileUiPart> = [
    { type: "text", text },
  ];
  const file = pageContextFileUiPart(ctx);
  if (file) parts.push(file);
  return parts;
}

function pageContextFromFilePart(part: {
  url?: string;
  mediaType?: string;
  filename?: string;
}): { text: string; html?: string; screenshotDataUrl?: string } | null {
  if (!isPageContextFilePart(part) || typeof part.url !== "string") return null;
  const raw = decodeDataUrlText(part.url);
  const screenshotDataUrl = raw.includes("digichat:page-context-screenshot")
    ? "data:image/png;base64,"
    : undefined;
  const textMatch = raw.match(/<!--\s*digichat:page-context-text\n([\s\S]*?)\n-->/);
  const supplement = textMatch?.[1]?.trim() ?? "";
  const body = raw
    .replace(/<!--\s*digichat:page-context-text\n[\s\S]*?\n-->/g, "")
    .replace(/\n?<!--\s*digichat:page-context-screenshot\s*-->/g, "")
    .trim();
  if (!body && !supplement && !screenshotDataUrl) return null;
  const html = (part.mediaType ?? "").includes("html");
  return html
    ? { text: supplement, html: body, screenshotDataUrl }
    : { text: body || supplement, screenshotDataUrl };
}

/**
 * Fold `page-context.html` file parts into the user text so convertToModelMessages
 * (text-only) still ships the snapshot to digigraph. Idempotent if already prefixed.
 */
export function expandPageContextFileParts<
  M extends {
    role: string;
    parts: Array<{ type: string; text?: string; filename?: string; url?: string; mediaType?: string }>;
  },
>(messages: M[]): M[] {
  return messages.map((m) => {
    if (m.role !== "user") return m;
    const fileParts = m.parts.filter((p) => isPageContextFilePart(p));
    if (fileParts.length === 0) return m;
    const question = m.parts
      .filter((p): p is { type: "text"; text: string } => p.type === "text")
      .map((p) => p.text)
      .join("");
    if (question.includes("[Page context from the host page")) {
      return {
        ...m,
        parts: m.parts.filter((p) => p.type === "text" || !isPageContextFilePart(p)),
      };
    }
    const ctx = pageContextFromFilePart(fileParts[0]!);
    const formatted = ctx ? formatPageContextForPrompt(ctx) : "";
    const text = formatted
      ? `${formatted}\n\n---\n\nUser question:\n${question}`
      : question;
    return {
      ...m,
      parts: [{ type: "text" as const, text }],
    };
  });
}