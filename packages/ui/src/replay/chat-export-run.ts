/**
 * Run an export: the conversation or one assistant message, as markdown or
 * HTML. Every skin's message menu and the chat-level `/export` call these,
 * so the formats, file names and errors are the same everywhere.
 */

import {
  chatExportStrings,
  conversationMarkdown,
  downloadMarkdown,
  lastQuestion,
  messageMarkdown,
  transcriptTurn,
  transcriptTurns,
  type ChatExportFormat,
  type ChatExportStrings,
} from "../components/chat/transcript";
import { isChatPrivateMode } from "../components/chat/stock/chat-private-mode";
import { downloadMessageSnapshot, downloadThreadSnapshot, showSnapshotError } from "./browser";
import { exportFilename } from "./filename";
import { deploymentText } from "./snapshot";

const EXPORT_FAILED = "Export failed.";

/**
 * A private session exports nothing: the stored messages still hold the real
 * typed text, and the file name carries a slug of the question. The menus
 * already hide the rows; this is the guard behind them.
 */
function exportBlocked(input: { privateMode?: boolean | undefined }): boolean {
  return input.privateMode === true || isChatPrivateMode();
}

function liveDocument(): Document | null {
  return typeof document === "undefined" ? null : document;
}

function reportError(doc: Document | null, error: unknown): void {
  const message = error instanceof Error ? error.message : EXPORT_FAILED;
  if (doc) showSnapshotError(doc, message);
  console.error("chat export failed", error);
}

export type ConversationExportInput = {
  format: ChatExportFormat;
  /** Runtime thread messages, in order. */
  messages: readonly unknown[];
  strings?: ChatExportStrings;
  doc?: Document | null;
  now?: string;
  /** The caller's private flag. The shared one is checked as well. */
  privateMode?: boolean | undefined;
};

/**
 * The whole conversation. Resolves after the file is handed to the browser.
 * Saves nothing in a private session.
 */
export async function exportConversation(input: ConversationExportInput): Promise<void> {
  if (exportBlocked(input)) return;
  const doc = input.doc === undefined ? liveDocument() : input.doc;
  const now = input.now ?? new Date().toISOString();
  try {
    if (input.format === "html") {
      await downloadThreadSnapshot(doc, now);
      return;
    }
    const turns = transcriptTurns(input.messages);
    const md = conversationMarkdown(turns, input.strings ?? chatExportStrings());
    if (!md) return;
    const deployment = doc ? deploymentText(doc) : "";
    downloadMarkdown(exportFilename(deployment, now, lastQuestion(turns), "md"), md);
  } catch (error) {
    reportError(doc, error);
  }
}

export type MessageExportInput = {
  format: ChatExportFormat;
  /** The assistant message's runtime state. */
  message: unknown;
  messageId: string;
  /** The thread's messages, for the question that names the file. */
  messages?: readonly unknown[];
  /** The menu trigger inside that message. HTML needs it to find the message. */
  trigger: HTMLElement | null;
  doc?: Document | null;
  now?: string;
  /** The caller's private flag. The shared one is checked as well. */
  privateMode?: boolean | undefined;
};

/**
 * One assistant message, without the question before it: the answer text
 * only, in both formats. Saves nothing in a private session.
 */
export async function exportMessage(input: MessageExportInput): Promise<void> {
  if (exportBlocked(input)) return;
  const doc = input.doc === undefined ? liveDocument() : input.doc;
  const now = input.now ?? new Date().toISOString();
  try {
    if (input.format === "html") {
      await downloadMessageSnapshot(doc, now, input.messageId, input.trigger);
      return;
    }
    const md = messageMarkdown(transcriptTurn(input.message));
    if (!md) return;
    const deployment = doc ? deploymentText(doc) : "";
    downloadMarkdown(exportFilename(deployment, now, messageQuestion(input), "md"), md);
  } catch (error) {
    reportError(doc, error);
  }
}

function messageQuestion(input: MessageExportInput): string {
  const all = input.messages ?? [];
  const index = all.findIndex(
    (m) => !!m && typeof m === "object" && (m as { id?: unknown }).id === input.messageId,
  );
  return index < 0 ? "" : lastQuestion(transcriptTurns(all.slice(0, index)));
}
