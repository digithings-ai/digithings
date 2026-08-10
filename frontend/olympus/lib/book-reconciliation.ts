import type { Position } from './types';

export interface ReconciledPosition extends Position {
  /** Weight normalized so held + cash = 100% (F3 single source of truth). */
  normalizedWeight: number;
  /** `weight_delta` carried into the normalized basis; null when no prior mark. */
  normalizedDelta?: number | null;
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

/** CASH is the invested/cash split, never a held row. */
function isCashTicker(ticker: string): boolean {
  return ticker.trim().toUpperCase() === 'CASH';
}

/**
 * Dedupe overlapping/double-counted `weight_pct` rows and normalize the held
 * book so held + cash = 100% (D1 / F3). Duplicates are the same holding listed
 * under multiple category buckets, so we keep the max weight per ticker.
 *
 * A CASH row is **excluded from the held set** (#1553): the pipeline emits
 * positions as % of NAV with an explicit CASH row (holdings sum to
 * `invested_pct`, CASH carries the rest). Folding that CASH row into `heldSum`
 * double-discounted every holding — it made `scale = invested / (held + cash)`,
 * shrinking real weights (UUP 40% → 36%), then counted cash a second time in
 * `cashPct`, so the displayed book summed to 91%, not 100%. Excluding CASH makes
 * `scale = invested / heldSum` land on ~1 for that shape (holdings render at
 * their true % of NAV) and is a no-op for the legacy shape with no CASH row.
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
    if (isCashTicker(p.ticker)) continue;
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
    normalizedDelta: p.weight_delta == null ? null : p.weight_delta * scale,
  }));

  const grossPct = rows.reduce((s, r) => s + Math.abs(r.normalizedWeight), 0);
  const netPct = rows.reduce(
    (s, r) => s + (r.type === 'SHORT' ? -r.normalizedWeight : r.normalizedWeight),
    0
  );
  return { rows, investedPct: invested, cashPct, grossPct, netPct };
}

/**
 * Held rows sorted by normalized weight, heaviest first — the basis for the
 * Brief holdings teaser (doorway). CASH is already excluded by `reconcileBook`;
 * the guard here keeps the selector correct for manually-built row lists too.
 */
export function heldByWeight(rows: ReconciledPosition[]): ReconciledPosition[] {
  return rows
    .filter((r) => !isCashTicker(r.ticker))
    .slice()
    .sort((a, b) => b.normalizedWeight - a.normalizedWeight);
}
