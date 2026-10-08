/**
 * Allowlisted monitor identity for the `trial_form` embed gate (DIG-613).
 *
 * An internal monitor — today the DataTap answer-integrity check — has no
 * sanctioned way past the free-turn gate. Without this it falls into the
 * per-client-IP bucket, spends the whole EMBED_FREE_TURN_LIMIT budget in the
 * first hour, and then reports 402 `trial_gate` on every later run. A reader
 * takes that 402 for a client's closed trial window when it is our own gate.
 *
 * The presented value is a server-side secret, compared against an allowlist in
 * DIGICHAT_MONITOR_TOKENS. It is deliberately NOT X-Embed-Token: that token is
 * a Stripe-style publishable key rendered into the embedding page on purpose,
 * so a bypass keyed on it would be a bypass every visitor already holds
 * (DIG-619). It is also not `x-embed-chat-token`, which belongs to the
 * consumeUrl quota path.
 *
 * Scope, stated plainly: the gate this unlocks is documented in
 * embed-turn-quota.ts as best-effort anti-abuse, NOT an authorization boundary.
 * This bypass therefore gives a monitor an unscoped turn budget, and nothing
 * more. It does not authenticate the caller, grant a tenant, or reach any other
 * check in the route — a caller still has to resolve a tenant context and
 * satisfy every other gate exactly as before.
 *
 * Fails open: when DIGICHAT_MONITOR_TOKENS is absent the predicate is false and
 * the gate behaves exactly as it does today. A missing deploy secret must not
 * become a reason to stop serving visitors.
 */

import { timingSafeEqual } from "node:crypto";

/** Header carrying the monitor secret. Distinct from every other embed header. */
export const EMBED_MONITOR_TOKEN_HEADER = "x-embed-monitor-token";

/**
 * Shortest value honoured as a monitor secret. Below this a value is guessable
 * or a mistake, so such an entry is ignored and the gate keeps its normal
 * behaviour rather than handing out an unscoped budget.
 */
export const MIN_MONITOR_TOKEN_LENGTH = 32;

function safeEqualStr(a: string, b: string): boolean {
  const ba = Buffer.from(a, "utf8");
  const bb = Buffer.from(b, "utf8");
  if (ba.length !== bb.length) return false;
  return timingSafeEqual(ba, bb);
}

/** Parsed, length-checked entries of DIGICHAT_MONITOR_TOKENS. */
function allowedTokens(): string[] {
  const raw = process.env.DIGICHAT_MONITOR_TOKENS;
  if (!raw) return [];
  return raw
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length >= MIN_MONITOR_TOKEN_LENGTH);
}

/**
 * True when the presented value matches an allowlisted monitor secret.
 *
 * Fails open: no allowlist configured, no header, or a value too short to be a
 * secret all return false, leaving the gate's normal per-IP behaviour intact.
 *
 * Compares against every entry without early exit so neither the number of
 * comparisons nor which entry matched is observable from timing.
 */
export function isAllowlistedMonitorToken(presented: string | null): boolean {
  const token = presented?.trim();
  if (!token || token.length < MIN_MONITOR_TOKEN_LENGTH) return false;

  let allowed = false;
  for (const entry of allowedTokens()) {
    // Fold with a bitwise OR: no branch that would stop at the first match.
    allowed = safeEqualStr(token, entry) || allowed;
  }
  return allowed;
}