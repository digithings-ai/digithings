/**
 * How a holding's size changed since the previous book date.
 *
 * The owner's rule, verbatim: *"if there was an add or a trim [show +/-], but if it was
 * completely removed or if it's a brand new position, then there isn't a rate of change to it.
 * It's just a brand new position or it's gone."*
 *
 * That distinction is the whole point. `weight_delta` in `queries.ts` used to compute
 * `weight - (prior ?? 0)`, so a brand-new 10% position reported `+10.0pp` — a rate of change for
 * something that had no prior size to change from. It reads as "we added 10 points to an existing
 * holding", which is a different event from "we opened a position". Same fabrication class as the
 * `0.0% → 0.0%` rebalance display (#1850) and the `0.0%` day-change on a carried price (#1833):
 * an absent value rendered as a real one.
 *
 * `null` weights mean "not held on that date", which is why they are distinct from `0` — a 0%
 * weight is a held-but-flat sleeve (the CASH row does this), and that genuinely can change.
 */
export type HoldingChangeKind = 'new' | 'gone' | 'increased' | 'decreased' | 'unchanged';

export interface HoldingWeightChange {
  kind: HoldingChangeKind;
  /**
   * Change in percentage points, or `null` when a delta is meaningless — i.e. for `new` and
   * `gone`. Consumers must not fall back to `0` here: zero means "held, and did not move".
   */
  deltaPp: number | null;
}

/** Below this, a difference is float noise from re-normalising weights, not a decision. */
const FLAT_EPSILON_PP = 0.01;

export function holdingWeightChange(
  currentPct: number | null | undefined,
  priorPct: number | null | undefined,
): HoldingWeightChange {
  const now = numeric(currentPct);
  const before = numeric(priorPct);

  // Not held on either date — nothing to say. Treated as `gone` rather than `unchanged` so a
  // caller never renders "0.0pp" for a row that is not in the book at all.
  if (now === null && before === null) return { kind: 'gone', deltaPp: null };
  if (before === null) return { kind: 'new', deltaPp: null };
  if (now === null) return { kind: 'gone', deltaPp: null };

  const delta = now - before;
  if (Math.abs(delta) < FLAT_EPSILON_PP) return { kind: 'unchanged', deltaPp: 0 };
  return { kind: delta > 0 ? 'increased' : 'decreased', deltaPp: delta };
}

/**
 * Day-over-day weight delta for holdings UI — null when there is no material book event
 * behind the move (#3080). Pure mark-to-market drift in `positions.weight_pct` must not
 * read as Added/Trimmed when the ledger recorded no decision-grade ADD/TRIM.
 */
export function holdingWeightDeltaPp(
  currentPct: number | null | undefined,
  priorPct: number | null | undefined,
  opts?: { hasMaterialBookEvent?: boolean },
): number | null {
  const change = holdingWeightChange(currentPct, priorPct);
  if (change.deltaPp === null) return null;
  if (change.kind === 'unchanged') return 0;
  if (opts?.hasMaterialBookEvent === false) return null;
  return change.deltaPp;
}

/**
 * The signed label for a change, or `null` when there is no rate of change to show.
 *
 * Returning `null` rather than an em-dash keeps the formatting decision with the component —
 * some surfaces want a dash, some want the badge omitted entirely.
 */
export function formatHoldingWeightChange(change: HoldingWeightChange): string | null {
  if (change.deltaPp === null) return null;
  if (change.kind === 'unchanged') return null;
  const sign = change.deltaPp > 0 ? '+' : '';
  return `${sign}${change.deltaPp.toFixed(1)}pp`;
}

function numeric(v: number | null | undefined): number | null {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
