/**
 * Parent → embed page context for the popup widget (#3421).
 *
 * The launcher may post visible-page text (and an optional screenshot data URL)
 * after `digichat:ready`. Only the immediate parent browsing context may send
 * this — never invent content behind auth the host page did not already show.
 */

export const PAGE_CONTEXT_MESSAGE_TYPE = "digichat:page-context" as const;

export const MAX_PAGE_CONTEXT_TEXT_CHARS = 8_000;
export const MAX_PAGE_CONTEXT_SCREENSHOT_CHARS = 400_000;
export const MAX_PAGE_CONTEXT_AGE_MS = 5 * 60 * 1000;

export type PageContextMessage = {
  type: typeof PAGE_CONTEXT_MESSAGE_TYPE;
  text: string;
  /** Optional `data:image/...;base64,...` from a same-document capture attempt. */
  screenshotDataUrl?: string;
  ts: number;
};

export function buildPageContextMessage(
  text: string,
  opts: { screenshotDataUrl?: string; ts?: number; maxChars?: number } = {},
): PageContextMessage {
  const max = opts.maxChars ?? MAX_PAGE_CONTEXT_TEXT_CHARS;
  const clipped = text.replace(/\s+/g, " ").trim().slice(0, max);
  const shot = opts.screenshotDataUrl?.trim();
  return {
    type: PAGE_CONTEXT_MESSAGE_TYPE,
    text: clipped,
    screenshotDataUrl:
      shot &&
      shot.startsWith("data:image/") &&
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
  let screenshotDataUrl: string | undefined;
  if (data.screenshotDataUrl !== undefined) {
    if (typeof data.screenshotDataUrl !== "string") return null;
    if (
      !data.screenshotDataUrl.startsWith("data:image/") ||
      data.screenshotDataUrl.length > MAX_PAGE_CONTEXT_SCREENSHOT_CHARS
    ) {
      return null;
    }
    screenshotDataUrl = data.screenshotDataUrl;
  }
  return {
    type: PAGE_CONTEXT_MESSAGE_TYPE,
    text: data.text,
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
 * Format page context for the next user turn. Screenshot is acknowledged but
 * not inlined as base64 into the chat prompt (too large); text is what the model sees.
 */
export function formatPageContextForPrompt(ctx: {
  text: string;
  screenshotDataUrl?: string;
}): string {
  const text = ctx.text.trim();
  if (!text && !ctx.screenshotDataUrl) return "";
  const lines = [
    "[Page context from the host page — content already visible to the visitor.]",
  ];
  if (text) lines.push(text);
  if (ctx.screenshotDataUrl) {
    lines.push("[A screenshot of the visible viewport was attached by the host widget.]");
  }
  return lines.join("\n");
}
