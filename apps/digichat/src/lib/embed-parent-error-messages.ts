/**
 * Parent → embed handshake / load failures for first-party digichat iframes.
 *
 * digithings.ai `ChatEmbedShell` posts `{ type: "digichat:parent-error", code, ts }`
 * when the ready handshake times out (or the iframe never loads). The embed
 * surfaces the line in CliThread's error row — same mono terminal aesthetic
 * as chat errors, not a parent-page banner.
 */

export const PARENT_ERROR_MESSAGE_TYPE = "digichat:parent-error" as const;

export type ParentErrorCode =
  | "ready_timeout"
  | "embed_unloadable"
  | "ready_target_missing";

export type ParentErrorMessage = {
  type: typeof PARENT_ERROR_MESSAGE_TYPE;
  code: ParentErrorCode;
  /** Optional override; prefer code→copy via formatParentErrorLine. */
  message?: string;
  ts: number;
};

/** Max age for a parent-error postMessage (ignore stale queued events). */
export const MAX_PARENT_ERROR_AGE_MS = 5 * 60 * 1000;

const PARENT_ERROR_CODES: ReadonlySet<string> = new Set([
  "ready_timeout",
  "embed_unloadable",
  "ready_target_missing",
]);

/**
 * Visitor-facing copy for each code. These lines render in the chat, so they
 * never name env vars, origins or container internals; operators read the
 * code itself (and the parent shell's dev console).
 */
function defaultParentErrorBody(code: ParentErrorCode): string {
  switch (code) {
    case "ready_timeout":
      return "the chat is taking longer than usual to start. Refresh to try again.";
    case "embed_unloadable":
      return "the chat could not load. Please try again in a moment.";
    case "ready_target_missing":
      return "the chat could not connect to this page. Refresh to try again.";
    default: {
      const _exhaustive: never = code;
      return _exhaustive;
    }
  }
}

/** CLI-style error line for CliThread's error row. */
export function formatParentErrorLine(
  code: ParentErrorCode,
  message?: string | null,
): string {
  const body = (message ?? "").trim() || defaultParentErrorBody(code);
  return `error: ${body}`;
}

export function buildParentErrorMessage(
  code: ParentErrorCode,
  opts?: { message?: string; ts?: number },
): ParentErrorMessage {
  const msg: ParentErrorMessage = {
    type: PARENT_ERROR_MESSAGE_TYPE,
    code,
    ts: opts?.ts ?? Date.now(),
  };
  if (opts?.message != null && opts.message.trim()) {
    msg.message = opts.message.trim();
  }
  return msg;
}

export function parseParentErrorMessage(
  event: MessageEvent,
  allowedParentOrigins: ReadonlySet<string>,
): ParentErrorMessage | null {
  if (!allowedParentOrigins.has(event.origin)) return null;
  const data = event.data as Record<string, unknown> | null;
  if (!data || data.type !== PARENT_ERROR_MESSAGE_TYPE) return null;
  if (typeof data.code !== "string" || !PARENT_ERROR_CODES.has(data.code)) {
    return null;
  }
  if (typeof data.ts !== "number") return null;
  if (Date.now() - data.ts > MAX_PARENT_ERROR_AGE_MS) return null;
  const code = data.code as ParentErrorCode;
  const message =
    typeof data.message === "string" && data.message.trim()
      ? data.message.trim()
      : undefined;
  return message
    ? { type: PARENT_ERROR_MESSAGE_TYPE, code, message, ts: data.ts }
    : { type: PARENT_ERROR_MESSAGE_TYPE, code, ts: data.ts };
}
