/**
 * postMessage contract for the trial-form gate (see the design spec's Global
 * Constraints). Two minimal `{ type }` messages, strict origin checks in both
 * directions, never targetOrigin "*". No credentials cross the boundary.
 */

export const GATED_MESSAGE = { type: "datatap:gated" } as const;
export const UNLOCKED_MESSAGE_TYPE = "datatap:unlocked";

/** True only for a well-formed unlock message from the exact known parent origin. */
export function isUnlockedMessage(
  event: MessageEvent,
  parentOrigin: string | undefined,
): boolean {
  if (!parentOrigin) return false;
  if (event.origin !== parentOrigin) return false;
  const data = event.data as { type?: unknown } | null;
  return !!data && data.type === UNLOCKED_MESSAGE_TYPE;
}

/** Caps mirrored by datatap-web's sanitizer and re-validated by the trial backend. */
export const MAX_GATED_SESSION_ID_CHARS = 200;
export const MAX_GATED_QUESTIONS = 3;
export const MAX_GATED_QUESTION_CHARS = 2000;

export type GatedMessage = {
  type: typeof GATED_MESSAGE.type;
  sessionId?: string;
  questions?: string[];
};

/**
 * Build the gated message, carrying the chat context that prompted the gate so the
 * embedding site can record which questions drove a trial signup.
 *
 * Best-effort by design: a missing session id or empty transcript yields a bare
 * `{ type }` message rather than blocking the gate. Fields are capped here and again
 * on the receiving side.
 */
export function buildGatedMessage(
  sessionId: string | null | undefined,
  messages: ReadonlyArray<{ role: string; content: string }>,
): GatedMessage {
  const id = (sessionId ?? "").trim().slice(0, MAX_GATED_SESSION_ID_CHARS);
  const questions = messages
    .filter((m) => m.role === "user")
    .map((m) => m.content.trim())
    .filter(Boolean)
    .slice(0, MAX_GATED_QUESTIONS)
    .map((q) => q.slice(0, MAX_GATED_QUESTION_CHARS));

  return {
    ...GATED_MESSAGE,
    ...(id ? { sessionId: id } : {}),
    ...(questions.length ? { questions } : {}),
  };
}
