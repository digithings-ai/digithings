import type { Position } from './types';

export interface ReconciledPosition extends Position {
  /** Weight normalized so held + cash = 100% (F3 single source of truth). */
  normalizedWeight: number;
}

export interface BookReconciliation {
  rows: ReconciledPosition[];
  investedPct: number;
  cashPct: number;
  /** Sum of |weights| — equals investedPct until the book is ever levered. */
  grossPct: number;
  /** Long − short — equals investedPct in a long-only book. */
  netPct: number;
}

/**
 * Dedupe overlapping/double-counted `weight_pct` rows and normalize the held
 * book so held + cash = 100% (D1 / F3). Duplicates are the same holding listed
 * under multiple category buckets, so we keep the max weight per ticker.
 *
 * `investedPct` (from nav_history / portfolio_metrics) is the authoritative
 * cash split when known; otherwise we fall back to the deduped held sum capped
 * at 100. Cash is always 100 − investedPct. Never returns a >100% book.
 */
export function reconcileBook(
  positions: Position[],
  opts: { investedPct?: number | null } = {}
): BookReconciliation {
  const byTicker = new Map<string, Position>();
  for (const p of positions) {
    const prev = byTicker.get(p.ticker);
    if (!prev || (p.weight_actual ?? 0) > (prev.weight_actual ?? 0)) {
      byTicker.set(p.ticker, p);
    }
  }
  const deduped = [...byTicker.values()];
  const heldSum = deduped.reduce((s, p) => s + (p.weight_actual ?? 0), 0);

  const invested =
    opts.investedPct != null && opts.investedPct >= 0
      ? Math.min(100, opts.investedPct)
      : Math.min(100, heldSum);
  const cashPct = Math.max(0, 100 - invested);

  // Scale deduped weights to the invested envelope (so they sum to investedPct).
  const scale = heldSum > 0 ? invested / heldSum : 0;
  const rows: ReconciledPosition[] = deduped.map((p) => ({
    ...p,
    normalizedWeight: (p.weight_actual ?? 0) * scale,
  }));

  const grossPct = rows.reduce((s, r) => s + Math.abs(r.normalizedWeight), 0);
  const netPct = rows.reduce(
    (s, r) => s + (r.type === 'SHORT' ? -r.normalizedWeight : r.normalizedWeight),
    0
  );
  return { rows, investedPct: invested, cashPct, grossPct, netPct };
}
