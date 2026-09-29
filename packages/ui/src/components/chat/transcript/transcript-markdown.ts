/**
 * Shared markdown serializer for digichat turn copy + full-thread export (#3465).
 *
 * Payload rules: keep fenced code / GFM tables; strip Foundry citation markers;
 * optional Sources lines from citation cards (title + path only — never vault body,
 * tool JSON, BYOK keys, or headers). Searching/tool rows and slash notes are omitted
 * because callers only pass user/assistant text turns.
 */

import { stripFoundryCitationMarkers } from "./activity-view";

export type TranscriptSource = {
  title: string;
  path: string;
};

export type TranscriptTurn = {
  role: "user" | "assistant";
  content: string;
  /** Citation cards already shown on that assistant turn (title + path only). */
  sources?: readonly TranscriptSource[];
};

export type CopyMarkdownResult = "clipboard" | "download" | "postMessage" | "textarea";

const COPY_POST_MESSAGE_TYPE = "digichat:copy";

/** Single-turn markdown — the string already fed to MiniMarkdown / ChatMarkdown. */
export function serializeAssistantMarkdown(
  content: string,
  sources?: readonly TranscriptSource[],
): string {
  const body = stripFoundryCitationMarkers(content).trim();
  const sourceBlock = formatSources(sources);
  if (!sourceBlock) return body;
  return body ? `${body}\n\n${sourceBlock}` : sourceBlock;
}

/** Full thread: `## You` / `## digichat` per text turn, in order. */
export function serializeThreadMarkdown(turns: readonly TranscriptTurn[]): string {
  const blocks: string[] = [];
  for (const turn of turns) {
    const heading = turn.role === "user" ? "## You" : "## digichat";
    const body =
      turn.role === "assistant"
        ? serializeAssistantMarkdown(turn.content, turn.sources)
        : turn.content.trim();
    if (!body) continue;
    blocks.push(`${heading}\n\n${body}`);
  }
  return blocks.join("\n\n");
}

function formatSources(sources?: readonly TranscriptSource[]): string {
  if (!sources?.length) return "";
  const lines = sources
    .map((s) => {
      const title = (s.title || s.path || "").trim();
      const path = (s.path || "").trim();
      if (!title && !path) return null;
      if (path && path !== title) return `- ${title} (${path})`;
      return `- ${title || path}`;
    })
    .filter((line): line is string => Boolean(line));
  if (!lines.length) return "";
  return `### Sources\n\n${lines.join("\n")}`;
}

/** Iframe-safe download — always available when `document` exists. */
export function downloadTextFile(filename: string, text: string, mime: string): void {
  if (typeof document === "undefined") {
    throw new Error("downloadTextFile requires a document");
  }
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Defer revoke — some browsers start the download asynchronously after click.
  const later = globalThis.setTimeout ?? ((fn: () => void) => {
    fn();
    return 0;
  });
  later(() => URL.revokeObjectURL(url), 2_000);
}

export function downloadMarkdown(filename: string, text: string): void {
  downloadTextFile(
    filename.endsWith(".md") ? filename : `${filename}.md`,
    text,
    "text/markdown;charset=utf-8",
  );
}

/** Plain-text export — same serializer output with fence delimiters stripped. */
export function downloadPlainText(filename: string, markdown: string): void {
  const name = filename.endsWith(".txt") ? filename : `${filename}.txt`;
  downloadTextFile(name, markdownToPlainText(markdown), "text/plain;charset=utf-8");
}

/** Minimal HTML export — pre-wrapped markdown, no renderer dependency. */
export function downloadHtml(filename: string, markdown: string, title = "digichat transcript"): void {
  const name = filename.endsWith(".html") ? filename : `${filename}.html`;
  downloadTextFile(name, markdownToHtmlDocument(markdown, title), "text/html;charset=utf-8");
}

function tryParentCopyPostMessage(text: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ type: COPY_POST_MESSAGE_TYPE, text }, "*");
      return true;
    }
  } catch {
    /* cross-origin access or blocked */
  }
  return false;
}

/**
 * Selectable textarea fallback when clipboard + download both fail.
 * Appends a temporary field, selects it, and focuses so the user can ⌘C.
 */
export function showSelectableTextareaFallback(text: string): void {
  if (typeof document === "undefined") return;
  const existing = document.getElementById("dc-copy-fallback");
  existing?.remove();
  const ta = document.createElement("textarea");
  ta.id = "dc-copy-fallback";
  ta.value = text;
  ta.setAttribute("aria-label", "Copy markdown");
  ta.readOnly = true;
  Object.assign(ta.style, {
    position: "fixed",
    left: "0.5rem",
    right: "0.5rem",
    bottom: "0.5rem",
    zIndex: "9999",
    width: "auto",
    maxHeight: "40vh",
    font: "12px/1.4 ui-monospace, monospace",
    padding: "0.5rem",
    border: "1px solid currentColor",
    background: "Canvas",
    color: "CanvasText",
  });
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
}

/**
 * Copy markdown with embed-safe fallbacks (#3465).
 *
 * Order: clipboard → `.md` download → optional parent `digichat:copy` postMessage →
 * selectable textarea. Never a silent no-op when `document` exists.
 */
export async function copyMarkdownWithFallback(
  text: string,
  opts?: { filename?: string },
): Promise<CopyMarkdownResult> {
  const filename = opts?.filename ?? "digichat.md";

  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return "clipboard";
    } catch {
      /* blocked in cross-origin iframes — continue */
    }
  }

  if (typeof document !== "undefined") {
    try {
      downloadMarkdown(filename, text);
      tryParentCopyPostMessage(text);
      return "download";
    } catch {
      /* fall through */
    }
  }

  if (tryParentCopyPostMessage(text)) {
    return "postMessage";
  }

  showSelectableTextareaFallback(text);
  return "textarea";
}

/* ---------------------------------------------------------------------------
 * Print + mailto + txt/html export (#3510). Reuses the #3465 serializers —
 * no vault bodies, tool JSON, or BYOK payloads ever enter these strings.
 * ------------------------------------------------------------------------- */

/** Safe `mailto:` body budget after `encodeURIComponent` (spec: ~1500–2000). */
export const MAILTO_MAX_ENCODED_LEN = 1800;

/** Appended when the mailto body is cut to fit the URL budget. */
export const MAILTO_TRUNCATION_NOTE = "…(truncated — download .md for full thread)";

export type TruncateForMailtoResult = { text: string; truncated: boolean };

/**
 * Cut `body` so `encodeURIComponent(text)` fits `maxEncoded` chars.
 * Binary-searches the longest fitting prefix, then appends the truncation
 * note. Pure — covered by vitest.
 */
export function truncateForMailto(
  body: string,
  maxEncoded: number = MAILTO_MAX_ENCODED_LEN,
): TruncateForMailtoResult {
  if (encodeURIComponent(body).length <= maxEncoded) {
    return { text: body, truncated: false };
  }
  const note = `\n\n${MAILTO_TRUNCATION_NOTE}`;
  if (encodeURIComponent(note).length >= maxEncoded) {
    let cut = note;
    while (cut.length > 1 && encodeURIComponent(`${cut}…`).length >= maxEncoded) {
      cut = cut.slice(0, -1);
    }
    return { text: cut, truncated: true };
  }
  let lo = 0;
  let hi = body.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    const candidate = body.slice(0, mid).trimEnd() + note;
    if (encodeURIComponent(candidate).length <= maxEncoded) {
      lo = mid;
    } else {
      hi = mid - 1;
    }
  }
  return { text: `${body.slice(0, lo).trimEnd()}${note}`, truncated: true };
}

/** `mailto:` URL with a short subject and a truncation-safe body. No network. */
export function buildMailtoUrl(
  subject: string,
  body: string,
  opts?: { maxEncoded?: number },
): string {
  const { text } = truncateForMailto(body, opts?.maxEncoded ?? MAILTO_MAX_ENCODED_LEN);
  return `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(text)}`;
}

/** Last-assistant mailto — mirrors the per-turn copy payload. */
export function buildAnswerMailto(markdown: string, opts?: { maxEncoded?: number }): string {
  return buildMailtoUrl("digichat answer", markdown, opts);
}

/** Full-thread mailto — mirrors the thread `.md` download payload. */
export function buildThreadMailto(markdown: string, opts?: { maxEncoded?: number }): string {
  return buildMailtoUrl("digichat transcript", markdown, opts);
}

export type MailtoOpenResult = "mailto" | "download";

export type ExportFallbackOpts = {
  fallbackMarkdown?: string;
  fallbackFilename?: string;
  /**
   * When true (embed / sandboxed iframe), skip mailto/print and download
   * immediately. Sandboxed embeds often expose `print` and allow `a.click()`
   * without throwing, so a try/catch-only fallback would silently no-op.
   */
  preferDownload?: boolean;
};

/**
 * Open a `mailto:` URL; on blocked navigation fall back to a `.md` download
 * (same spirit as the #3465 clipboard fallback). Never throws when `document`
 * exists — worst case the caller gets `"download"`.
 */
export function openMailtoWithFallback(
  mailtoUrl: string,
  opts?: ExportFallbackOpts,
): MailtoOpenResult {
  const fallback = () => {
    if (opts?.fallbackMarkdown !== undefined && typeof document !== "undefined") {
      try {
        downloadMarkdown(opts.fallbackFilename ?? "digichat-thread.md", opts.fallbackMarkdown);
      } catch {
        /* download also blocked — caller already has the markdown */
      }
    }
  };
  if (!mailtoUrl.startsWith("mailto:")) {
    fallback();
    return "download";
  }
  if (opts?.preferDownload || typeof document === "undefined") {
    fallback();
    return "download";
  }
  try {
    const a = document.createElement("a");
    a.href = mailtoUrl;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    return "mailto";
  } catch {
    fallback();
    return "download";
  }
}

export type PrintTranscriptResult = "print" | "download";

/**
 * `window.print()` for the transcript; when print is unavailable/blocked
 * (no window, embed sandbox), fall back to a `.md` download so the action
 * is never a silent no-op.
 */
export function printTranscriptWithFallback(
  opts?: ExportFallbackOpts,
): PrintTranscriptResult {
  const fallback = () => {
    if (opts?.fallbackMarkdown !== undefined && typeof document !== "undefined") {
      try {
        downloadMarkdown(opts.fallbackFilename ?? "digichat-thread.md", opts.fallbackMarkdown);
      } catch {
        /* ignore — print already failed */
      }
    }
  };
  if (opts?.preferDownload) {
    fallback();
    return "download";
  }
  if (typeof window !== "undefined" && typeof window.print === "function") {
    try {
      window.print();
      return "print";
    } catch {
      fallback();
      return "download";
    }
  }
  fallback();
  return "download";
}

/**
 * Lightweight markdown → plain text for `.txt` export. Strips fence
 * delimiter lines only; prose (including code content) is kept as-is.
 */
export function markdownToPlainText(markdown: string): string {
  return markdown
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("```"))
    .join("\n")
    .trim();
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Minimal HTML document for `.html` export — the markdown pre-wrapped in
 * `<pre>`. Deliberately no GFM renderer dependency.
 */
export function markdownToHtmlDocument(markdown: string, title = "digichat transcript"): string {
  const safeTitle = escapeHtml(title);
  const safeBody = escapeHtml(markdown);
  return [
    "<!doctype html>",
    '<html lang="en">',
    "<head>",
    '<meta charset="utf-8">',
    `<title>${safeTitle}</title>`,
    "</head>",
    "<body>",
    `<h1>${safeTitle}</h1>`,
    `<pre>${safeBody}</pre>`,
    "</body>",
    "</html>",
    "",
  ].join("\n");
}
