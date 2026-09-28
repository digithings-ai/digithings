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

/** Max token length accepted off the wire — {32-hex id}.{44-char base64 secret} plus slack. */
const MAX_UNLOCK_TOKEN_CHARS = 512;

/**
 * The chat-access token carried on an unlock message, or null when absent or implausible.
 * Call ONLY after isUnlockedMessage() has verified the origin — this performs no origin check,
 * so the origin rule stays in exactly one place.
 */
export function readUnlockToken(event: MessageEvent): string | null {
  const data = event.data as { token?: unknown } | null;
  if (!data || typeof data.token !== "string") return null;
  const token = data.token.trim();
  if (!token || token.length > MAX_UNLOCK_TOKEN_CHARS) return null;
  return token;
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

/**
 * Fallback timeout (design spec, "Error handling & fallbacks"): once the embed
 * has posted `datatap:gated` to a parent, a healthy parent immediately covers
 * the whole iframe with its own full-bleed overlay (`position:absolute;
 * inset:0; z-index:20`) and shows the trial form there. If no `datatap:unlocked`
 * reply arrives within this window — parent on an old build, its JS threw, a
 * CSP or extension blocked the listener — the embed swaps its own
 * "complete the form" placeholder for the lockedContact mailto card so the
 * visitor always has a way to reach out. 8s is long enough that ordinary slow
 * parent JS never causes a visible flash of the fallback (the overlay would
 * already be covering it), short enough that a genuinely unanswered visitor
 * isn't left stuck for long.
 */
export const PARENT_GATE_TIMEOUT_MS = 8000;

export type GateFallbackInputs = {
  /** No channel to a parent exists at all (standalone, or embed missing `?host=`). */
  noParentChannel: boolean;
  /** PARENT_GATE_TIMEOUT_MS elapsed after posting `datatap:gated` with no unlock reply. */
  parentUnresponsive: boolean;
};

export type GateFallbackCard = "paywall" | "placeholder";

/**
 * Which formReplacement card a locked trial-form embed should render.
 * "paywall" is the lockedContact mailto card — a real, actionable fallback.
 * "placeholder" is "complete the form to keep chatting", which is only safe
 * to show when a working parent is guaranteed to cover it with its own
 * overlay; either reason to distrust that guarantee routes to "paywall".
 */
export function resolveGateFallbackCard({
  noParentChannel,
  parentUnresponsive,
}: GateFallbackInputs): GateFallbackCard {
  return noParentChannel || parentUnresponsive ? "paywall" : "placeholder";
}
