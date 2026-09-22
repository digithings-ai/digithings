/**
 * PM position rationale for Brief / actions UI.
 *
 * Historical `pm-rebalance` rows often carry the H8 mechanical fallback
 * ("Position weight set by deterministic risk sizing.") even when H7 already
 * published a real roster narrative. Never surface that boilerplate as a
 * "reason" — prefer usable PM thesis text, else show action + ticker only.
 *
 * Position-event rows written by execute_at_open's derived fallback also leak
 * engineering internals (`proposed_positions`, `rebalance_decision.json`) —
 * those never belong in desk copy either.
 */

const MECHANICAL_SIZING_RE =
  /^(position\s+)?weight\s+set\s+by\s+deterministic\s+risk\s+sizing\.?$/i;

/** execute_at_open / backfill prose that names pipeline artifacts. */
const DERIVED_BOOK_REASON_RE =
  /derived from positions book|proposed_positions|rebalance_decision\.json|digest (proposed_positions )?unavailable/i;

/** True when the string is empty or the known H8 sizing fallback (and close variants). */
export function isMechanicalSizingRationale(raw: string | null | undefined): boolean {
  const t = (raw ?? '').replace(/\s+/g, ' ').trim();
  if (!t) return true;
  return MECHANICAL_SIZING_RE.test(t);
}

/** True when the string is execute_at_open derived-fallback engineering copy. */
export function isDerivedBookReason(raw: string | null | undefined): boolean {
  const t = (raw ?? '').replace(/\s+/g, ' ').trim();
  if (!t) return false;
  return DERIVED_BOOK_REASON_RE.test(t);
}

/** Return trimmed rationale, or null when empty / non-desk boilerplate. */
export function usablePmRationale(raw: string | null | undefined): string | null {
  const t = (raw ?? '').replace(/\s+/g, ' ').trim();
  if (!t || isMechanicalSizingRationale(t) || isDerivedBookReason(t)) return null;
  return t;
}
