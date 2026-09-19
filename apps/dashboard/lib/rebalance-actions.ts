import type { RebalanceAction } from './types';

/**
 * Build the displayable rebalance actions from a `pm-rebalance` document's `actions` array.
 *
 * Extracted from `queries.ts` so it can be tested: the module it came from is a large
 * Supabase-fetching surface with no harness, and this arithmetic had a bug that reached users
 * (#1850) precisely because nothing exercised it.
 *
 * ## The bug this exists to prevent
 *
 * The live payload carries only `{action, ticker, rationale, target_pct}` — verified against the
 * 2026-08-04 document. There is no `current_pct` key at all. The old code read
 * `Number(o.current_pct ?? 0)`, so every action rendered as starting from **0.0%**: a trim from
 * 30% to 15% displayed as "0.0% → 15.0%", which is why day-to-day position changes were
 * unreadable on the dashboard.
 *
 * ## Where the prior weight actually lives — and where it does NOT
 *
 * It is the ticker's weight on the **previous** book date, not the current one. This is the
 * trap: the current book already has the target applied. On 2026-08-04 XLV's stored `weight_pct`
 * was 5.0 and its `target_pct` was also 5.0, so reading the current book yields "5.0% → 5.0%" —
 * no change at all, a different wrong answer. The real move was 9.86% → 5.0%, and 9.86% is on
 * 08-03.
 *
 * A ticker with no prior-date weight genuinely was not held, so 0% is a real value there rather
 * than a fabricated one — that case is an OPEN, and the panel labels it as such.
 */
export function buildRebalanceActions(
  actions: unknown,
  prevWeightByTicker: Map<string, number>,
): RebalanceAction[] {
  if (!Array.isArray(actions)) return [];
  const out: RebalanceAction[] = [];
  for (const a of actions) {
    if (!a || typeof a !== 'object') continue;
    const o = a as Record<string, unknown>;
    const ticker = String(o.ticker || '')
      .trim()
      .toUpperCase();
    if (!ticker) continue;
    out.push({
      ticker,
      current_pct: Number(o.current_pct ?? prevWeightByTicker.get(ticker) ?? 0),
      // Live shape: `target_pct`; fixture / test payloads: `recommended_pct`.
      recommended_pct: Number(o.target_pct ?? o.recommended_pct ?? 0),
      action: String(o.action || 'HOLD').toUpperCase(),
      // Carry rationale so downstream UI can render it without another fetch.
      ...(o.rationale != null ? { rationale: String(o.rationale) } : {}),
    });
  }
  return out;
}

/** Desk display precision for rebalance weight moves (1 decimal pp). */
const DESK_PP_DECIMALS = 1;

/** Signed target − current in pp, or null when it rounds to 0.0pp at desk precision. */
export function rebalanceDeltaPp(action: RebalanceAction): number | null {
  const from = action.current_pct ?? 0;
  const to = action.recommended_pct ?? 0;
  const delta = to - from;
  if (!Number.isFinite(delta)) return null;
  if (Number(delta.toFixed(DESK_PP_DECIMALS)) === 0) return null;
  return delta;
}

/** Non-HOLD book moves that are material at desk display precision (#3080). */
export function isMaterialRebalanceAction(action: RebalanceAction): boolean {
  const kind = (action.action || '').trim().toUpperCase();
  if (kind === 'HOLD') return false;
  if (kind === 'EXIT' && (action.current_pct ?? 0) === 0) return false;
  if (kind === 'ADD' || kind === 'TRIM' || kind === 'INCREASE' || kind === 'DECREASE') {
    return rebalanceDeltaPp(action) !== null;
  }
  return true;
}
