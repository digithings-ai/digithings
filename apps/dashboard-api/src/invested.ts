/**
 * Invested-% precedence for the dashboard-api worker (slice 0003).
 *
 * Server-side port of `resolveInvestedPct` in
 * `apps/dashboard/lib/performance-ssot.ts` (used by
 * `PortfolioShellInner.tsx` for the holdings tile). Contract §6.1 fallback
 * order: NAV tip → non-CASH book-weight sum on the committed book →
 * `portfolio_metrics.invested_pct` → null.
 *
 * `kpi_pct` is the raw resolved value — do NOT clamp >100 under an
 * accounting-tip label. Row weights are laid out inside the separate
 * clamped-100 `reconcileBook` envelope (`envelope_pct`); that envelope is
 * not the KPI.
 *
 * Pure logic — no I/O, no secrets, no time/tool-call budgets.
 */

export type InvestedDefinition =
  /** Tip row of `public_accounting_nav_history.invested_pct`. */
  | 'accounting_nav_tip'
  /** Sum of non-CASH `positions.weight_pct` on the committed book date. */
  | 'book_weights'
  /** Stale/secondary — `portfolio_metrics.invested_pct` when NAV tip missing. */
  | 'portfolio_metrics'
  /** No invested source available — do not claim an accounting tip. */
  | 'unavailable';

export interface InvestedResolution {
  investedPct: number | null;
  definition: InvestedDefinition;
}

/**
 * Prefer the accounting NAV tip invested %; else book weights; else metrics.
 * Never silently mix live weights with book weights for the invested tile.
 */
export function resolveInvestedPct(args: {
  tipInvestedPct: number | null | undefined;
  bookWeightInvestedPct: number | null | undefined;
  metricsInvestedPct: number | null | undefined;
}): InvestedResolution {
  if (
    args.tipInvestedPct != null &&
    Number.isFinite(args.tipInvestedPct) &&
    args.tipInvestedPct >= 0
  ) {
    return { investedPct: args.tipInvestedPct, definition: 'accounting_nav_tip' };
  }
  if (
    args.bookWeightInvestedPct != null &&
    Number.isFinite(args.bookWeightInvestedPct) &&
    args.bookWeightInvestedPct >= 0
  ) {
    return { investedPct: args.bookWeightInvestedPct, definition: 'book_weights' };
  }
  if (
    args.metricsInvestedPct != null &&
    Number.isFinite(args.metricsInvestedPct) &&
    args.metricsInvestedPct >= 0
  ) {
    return { investedPct: args.metricsInvestedPct, definition: 'portfolio_metrics' };
  }
  return { investedPct: null, definition: 'unavailable' };
}

export interface InvestedEnvelope {
  /** Raw resolved KPI — unclamped, even above 100 under an accounting tip. */
  kpiPct: number | null;
  /** Clamped-100 envelope rows are scaled into (the `reconcileBook` basis). */
  envelopePct: number | null;
  cashPct: number | null;
  definition: InvestedDefinition;
}

/**
 * Split the resolved invested % into the §6.1 display pair: the raw KPI plus
 * the clamped envelope that allocation rows scale into. `heldSum` is the
 * deduped non-CASH book-weight sum (used only when no resolved source won).
 */
export function buildInvestedEnvelope(
  resolved: InvestedResolution,
  heldSum: number,
): InvestedEnvelope {
  if (resolved.investedPct == null) {
    const envelope = Math.min(100, Math.max(0, heldSum));
    return {
      kpiPct: null,
      envelopePct: envelope,
      cashPct: Math.max(0, 100 - envelope),
      definition: resolved.definition,
    };
  }
  const envelope = Math.min(100, resolved.investedPct);
  return {
    kpiPct: resolved.investedPct,
    envelopePct: envelope,
    cashPct: Math.max(0, 100 - envelope),
    definition: resolved.definition,
  };
}
