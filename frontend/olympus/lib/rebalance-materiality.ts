import type { RebalanceAction } from './types';

/**
 * Desk-display materiality for rebalance actions (#3080).
 *
 * Hermes already suppresses in-band weight churn via the no-trade band. The dashboard
 * still used to surface ADD/TRIM rows whose arrow rounded to `0.0pp` (or HOLD rows whose
 * prior-book → drifted-target pair looked like a micro move). Reuse the same 1-decimal
 * pp rule as `isMaterialBookEvent` — not a new hard floor on the sizer.
 */

export function rebalanceDeltaPp(action: RebalanceAction): number {
  return (action.recommended_pct ?? 0) - (action.current_pct ?? 0);
}

/** True when the weight move rounds to a non-zero 1-decimal pp change (desk display). */
export function isMaterialRebalanceDelta(action: RebalanceAction): boolean {
  return Number(rebalanceDeltaPp(action).toFixed(1)) !== 0;
}

/**
 * Book-building actions the Brief / hero should surface.
 * HOLD is never active; EXIT at 0% current is a sizer no-op; ADD/TRIM that round to
 * 0.0pp are display noise, not a trade.
 */
export function isActiveRebalanceAction(action: RebalanceAction): boolean {
  const kind = (action.action || '').trim().toUpperCase();
  if (kind === 'HOLD') return false;
  if (kind === 'EXIT' && (action.current_pct ?? 0) === 0) return false;
  if (kind === 'ADD' || kind === 'TRIM' || kind === 'INCREASE' || kind === 'DECREASE') {
    return isMaterialRebalanceDelta(action);
  }
  // OPEN / NEW / EXIT (with weight) always count.
  return true;
}
