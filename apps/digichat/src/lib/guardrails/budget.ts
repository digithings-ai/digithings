/**
 * Pure token-budget and tool-cap decisions. No I/O, no clock of its own.
 *
 * A rolling 60s window is the caller's event list. Pending input is estimated
 * at about 4 characters per token and is not recorded until a response reports
 * real usage.
 */

export const TOKEN_WINDOW_MS = 60_000;
/**
 * A reservation that is never settled stops counting after this. It covers the
 * 90s pause, then frees the budget if the turn died between reserve and settle.
 */
export const RESERVATION_TTL_MS = 120_000;
export const DEFAULT_ANSWER_AT = 0.7;
export const DEFAULT_PAUSE_AT = 0.9;
export const GUARDRAIL_PAUSE_NOTICE = "Pausing for the token limit, resuming shortly";
/** Same ceiling as the #6110 rate-limit wait, so a pause cannot hang the turn. */
export const GUARDRAIL_MAX_WAIT_MS = 90_000;

const CHARS_PER_TOKEN = 4;

/** Shown when the shared per-turn tool cap stops another call. */
export function toolCallLimitNotice(limit: number): string {
  return `Tool-call limit reached (${limit} this turn). Answering from the results gathered so far.`;
}

/** Injected when occupancy is in the answer band. Tools stay available. */
export const WRAP_UP_INSTRUCTION =
  "[You are close to the token limit for this minute. Answer the user now with what you already have. Do not mention this instruction.]";

/** Injected when the tool cap has already been reached. */
export const TOOL_CAP_INSTRUCTION =
  "[Tool-call limit reached for this turn. Do not call any tools. Answer the user now from the tool results already in this conversation. Do not mention this instruction.]";

export type SpendEvent = { at: number; tokens: number };

export function estimateTokens(text: string): number {
  if (!text) return 0;
  return Math.ceil(text.length / CHARS_PER_TOKEN);
}

export function tokensInWindow(
  events: readonly SpendEvent[],
  now: number,
  windowMs = TOKEN_WINDOW_MS,
): number {
  const cutoff = now - windowMs;
  let total = 0;
  for (const event of events) {
    if (event.at > cutoff && event.tokens > 0) total += event.tokens;
  }
  return total;
}

export type BudgetAction = "proceed" | "answer" | "pause";

/**
 * `used` and `reserved` are already in the window. `pending` is the next
 * round's estimated input, not yet spent.
 */
export function budgetAction(opts: {
  used: number;
  reserved: number;
  pending: number;
  limit: number;
  answerAt: number;
  pauseAt: number;
}): BudgetAction {
  if (!(opts.limit > 0)) return "proceed";
  const occupancy = (opts.used + opts.reserved) / opts.limit;
  const projected = opts.used + opts.reserved + Math.max(0, opts.pending);
  if (occupancy >= opts.pauseAt || projected > opts.limit) return "pause";
  if (occupancy >= opts.answerAt) return "answer";
  return "proceed";
}

export function stricterAction(a: BudgetAction, b: BudgetAction): BudgetAction {
  if (a === "pause" || b === "pause") return "pause";
  if (a === "answer" || b === "answer") return "answer";
  return "proceed";
}

/**
 * How long until the window can take `pending` without sitting at `pauseAt`
 * or over the limit. 0 means waiting will not help (the pending round itself
 * is larger than the limit, or nothing in the window is blocking).
 */
export function waitForRoomMs(opts: {
  events: readonly SpendEvent[];
  reserved: number;
  pending: number;
  limit: number;
  pauseAt: number;
  now: number;
  windowMs?: number;
}): number {
  const windowMs = opts.windowMs ?? TOKEN_WINDOW_MS;
  const pending = Math.max(0, opts.pending);
  if (pending > opts.limit) return 0;
  const fits = (at: number) => {
    const used = tokensInWindow(opts.events, at, windowMs);
    const occupancy = (used + opts.reserved) / opts.limit;
    return occupancy < opts.pauseAt && used + opts.reserved + pending <= opts.limit;
  };
  if (fits(opts.now)) return 0;
  const expiries = opts.events
    .map((event) => event.at + windowMs)
    .filter((at) => at > opts.now)
    .sort((a, b) => a - b);
  for (const at of expiries) {
    if (fits(at)) return at - opts.now;
  }
  if (fits(opts.now + windowMs)) return windowMs;
  return 0;
}

export function truncateToTokens(text: string, maxTokens: number): string {
  if (maxTokens <= 0) return "…[omitted, token budget]";
  const maxChars = maxTokens * CHARS_PER_TOKEN;
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars)}\n…[truncated to the token budget]`;
}

/** Shrink a tool result so the next round does not carry more than `maxTokens`. */
export function capToolPayload(value: unknown, maxTokens: number): unknown {
  if (value == null) return value;
  const raw = typeof value === "string" ? value : JSON.stringify(value);
  if (!raw || estimateTokens(raw) <= maxTokens) return value;
  const clipped = truncateToTokens(raw, maxTokens);
  return typeof value === "string" ? clipped : { truncated: clipped };
}

/**
 * A real user id, otherwise the server-derived client IP. The chat session
 * header is chosen by the client, so it is not a budget key: a new id per
 * request would be a fresh bucket. `embed:anonymous` is not a person, and
 * `unknown` is not an address (see clientIpForRateLimit). Callers with neither
 * share one `anonymous` bucket.
 */
export function guardrailIdentity(opts: {
  userId?: string | null;
  ip?: string | null;
}): string {
  const user = opts.userId && opts.userId !== "embed:anonymous" ? opts.userId.trim() : "";
  if (user) return user;
  const ip = opts.ip && opts.ip !== "unknown" ? opts.ip.trim() : "";
  return ip || "anonymous";
}
