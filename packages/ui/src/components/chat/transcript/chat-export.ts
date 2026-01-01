/**
 * One export model for every skin: a format (`md` | `html`) and a scope.
 *
 * - The message menu exports that assistant message only.
 * - The chat menu (`/export`, the settings list) exports the whole
 *   conversation, user and assistant turns in order.
 *
 * Markdown is built from the runtime messages. HTML is a snapshot of the
 * rendered thread (`replay/browser`), so it looks like the chat.
 */

import { serializeAssistantMarkdown, type TranscriptTurn } from "./transcript-markdown";

export type ChatExportFormat = "md" | "html";

export const CHAT_EXPORT_FORMATS: readonly ChatExportFormat[] = ["md", "html"];

/** `md`, `markdown`, `html`, case-insensitive. Empty means markdown. */
export function parseChatExportFormat(raw: string | null | undefined): ChatExportFormat | null {
  const value = (raw ?? "").trim().toLowerCase().replace(/^\./, "");
  if (value === "" || value === "md" || value === "markdown") return "md";
  if (value === "html" || value === "htm") return "html";
  return null;
}

export type ChatExportStrings = {
  /** The submenu trigger: `Export`. */
  export: string;
  markdown: string;
  html: string;
  /** Hint under the chat-level `/export` row. */
  conversationHint: string;
  /** Turn headings in the markdown file. */
  user: string;
  assistant: string;
};

const EN: ChatExportStrings = {
  export: "Export",
  markdown: "Markdown (.md)",
  html: "HTML (.html)",
  conversationHint: "Download this conversation as a file.",
  user: "User",
  assistant: "Assistant",
};

const FR: ChatExportStrings = {
  export: "Exporter",
  markdown: "Markdown (.md)",
  html: "HTML (.html)",
  conversationHint: "Télécharger cette conversation dans un fichier.",
  user: "Utilisateur",
  assistant: "Assistant",
};

export const CHAT_EXPORT_LOCALES: Readonly<Record<string, ChatExportStrings>> = { en: EN, fr: FR };

/** Strings for a language code (`fr`, `fr-CA`). Unknown languages get English. */
export function chatExportStrings(locale?: string | null): ChatExportStrings {
  const code = (locale ?? "").split(/[-_]/)[0]?.toLowerCase() ?? "";
  return CHAT_EXPORT_LOCALES[code] ?? EN;
}

export function chatExportLabel(format: ChatExportFormat, strings: ChatExportStrings): string {
  return format === "html" ? strings.html : strings.markdown;
}

/**
 * Text turns from runtime messages (`content` or `parts`). Tool calls,
 * reasoning and empty turns are left out.
 */
export function transcriptTurns(messages: readonly unknown[]): TranscriptTurn[] {
  const out: TranscriptTurn[] = [];
  for (const raw of messages) {
    const turn = transcriptTurn(raw);
    if (turn) out.push(turn);
  }
  return out;
}

export function transcriptTurn(raw: unknown): TranscriptTurn | null {
  if (!raw || typeof raw !== "object") return null;
  const m = raw as { role?: string; content?: unknown; parts?: unknown };
  if (m.role !== "user" && m.role !== "assistant") return null;
  const parts = Array.isArray(m.content) ? m.content : m.parts;
  const text = Array.isArray(parts)
    ? parts
        .filter((p): p is { type: string; text?: string } => !!p && typeof p === "object")
        .filter((p) => p.type === "text" && typeof p.text === "string")
        .map((p) => p.text ?? "")
        .join("")
    : typeof m.content === "string"
      ? m.content
      : "";
  if (!text.trim()) return null;
  return { role: m.role, content: text };
}

/**
 * The conversation file: a `## User` / `## Assistant` heading per turn, in
 * order, separated by a rule so the turns stay apart in any viewer.
 */
export function conversationMarkdown(
  turns: readonly TranscriptTurn[],
  strings: Pick<ChatExportStrings, "user" | "assistant"> = EN,
): string {
  const blocks: string[] = [];
  for (const turn of turns) {
    const body =
      turn.role === "assistant"
        ? serializeAssistantMarkdown(turn.content, turn.sources)
        : turn.content.trim();
    if (!body) continue;
    const heading = turn.role === "user" ? strings.user : strings.assistant;
    blocks.push(`## ${heading}\n\n${body}`);
  }
  return blocks.join("\n\n---\n\n");
}

/** One assistant message, as rendered: no heading, no question. */
export function messageMarkdown(turn: TranscriptTurn | null): string {
  if (!turn || turn.role !== "assistant") return "";
  return serializeAssistantMarkdown(turn.content, turn.sources);
}

/** Last user question in the turns, for the file name. */
export function lastQuestion(turns: readonly TranscriptTurn[]): string {
  for (let i = turns.length - 1; i >= 0; i -= 1) {
    const turn = turns[i];
    if (turn?.role === "user") return turn.content;
  }
  return "";
}
