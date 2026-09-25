/**
 * Committed-book reconciliation for the dashboard-api worker (slice 0003).
 *
 * Server-side port of the client derivation in
 * `apps/dashboard/lib/book-reconciliation.ts` (`reconcileBook`). Behavior must
 * stay identical: dedupe overlapping rows, exclude CASH from the held set,
 * scale held weights into the clamped-100 invested envelope. Parity tests in
 * `book.test.ts` mirror the client cases (including the #1553 CASH shape).
 *
 * Pure logic — no I/O, no secrets, no time/tool-call budgets.
 */

export interface BookPositionInput {
  ticker: string;
  /** Weight as % of NAV (`weight_actual` on the client `Position`). */
  weightActual: number | null | undefined;
  type?: 'LONG' | 'SHORT' | string | null;
  /** Change vs previous positions date, in percentage points. */
  weightDelta?: number | null | undefined;
}

export interface ReconciledRow {
  ticker: string;
  /** Raw deduped weight as % of NAV. */
  weightPct: number;
  /** Weight scaled into the invested envelope (sums to `investedPct`). */
  scaledWeightPct: number;
  /** `weightDelta` carried into the scaled basis; null when no prior mark. */
  scaledDelta: number | null;
  isShort: boolean;
}

export interface BookReconciliation {
  rows: ReconciledRow[];
  investedPct: number;
  cashPct: number;
  /** Sum of |scaled| weights — equals investedPct until the book is levered. */
  grossPct: number;
  /** Long − short — equals investedPct in a long-only book. */
  netPct: number;
}

/** CASH is the invested/cash split, never a held row. */
export function isCashTicker(ticker: string): boolean {
  return ticker.trim().toUpperCase() === 'CASH';
}

/**
 * Dedupe overlapping/double-counted weight rows and scale the held book so
 * held + cash = 100%. Duplicates are the same holding listed under multiple
 * category buckets — keep the max weight per ticker.
 *
 * A CASH row is excluded from the held set (#1553): the pipeline emits
 * holdings as % of NAV with an explicit CASH row, so folding it into the held
 * sum would double-discount every holding and double-count cash.
 *
 * `investedPct` (resolved invested, e.g. the NAV tip) is the authoritative
 * envelope when known; otherwise fall back to the deduped held sum capped at
 * 100. Cash is always 100 − investedPct. Never returns a >100% book.
 */
export function reconcileBook(
  positions: ReadonlyArray<BookPositionInput>,
  opts: { investedPct?: number | null } = {},
): BookReconciliation {
  const byTicker = new Map<string, BookPositionInput>();
  for (const p of positions) {
    if (isCashTicker(p.ticker)) continue;
    const prev = byTicker.get(p.ticker);
    if (!prev || (p.weightActual ?? 0) > (prev.weightActual ?? 0)) {
      byTicker.set(p.ticker, p);
    }
  }
  const deduped = [...byTicker.values()];
  const heldSum = deduped.reduce((s, p) => s + (p.weightActual ?? 0), 0);

  const invested =
    opts.investedPct != null && opts.investedPct >= 0
      ? Math.min(100, opts.investedPct)
      : Math.min(100, heldSum);
  const cashPct = Math.max(0, 100 - invested);

  const scale = heldSum > 0 ? invested / heldSum : 0;
  const rows: ReconciledRow[] = deduped.map((p) => ({
    ticker: p.ticker,
    weightPct: p.weightActual ?? 0,
    scaledWeightPct: (p.weightActual ?? 0) * scale,
    scaledDelta: p.weightDelta == null ? null : p.weightDelta * scale,
    isShort: p.type === 'SHORT',
  }));

  const grossPct = rows.reduce((s, r) => s + Math.abs(r.scaledWeightPct), 0);
  const netPct = rows.reduce(
    (s, r) => s + (r.isShort ? -r.scaledWeightPct : r.scaledWeightPct),
    0,
  );
  return { rows, investedPct: invested, cashPct, grossPct, netPct };
}

/**
 * Held rows sorted by scaled weight, heaviest first — the basis for the
 * holdings teaser. CASH is already excluded by `reconcileBook`; the guard
 * keeps the selector correct for manually-built row lists too.
 */
export function heldByWeight(rows: ReadonlyArray<ReconciledRow>): ReconciledRow[] {
  return rows
    .filter((r) => !isCashTicker(r.ticker))
    .slice()
    .sort((a, b) => b.scaledWeightPct - a.scaledWeightPct);
}
