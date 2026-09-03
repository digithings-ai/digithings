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
export function downloadMarkdown(filename: string, text: string): void {
  if (typeof document === "undefined") {
    throw new Error("downloadMarkdown requires a document");
  }
  const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".md") ? filename : `${filename}.md`;
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
