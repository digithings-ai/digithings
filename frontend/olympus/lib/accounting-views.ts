/**
 * Curated Olympus / digiquant.io accounting read surface (#2599 / Task 3.4).
 *
 * Prefer these view names in adapters. Rollback = repoint to LEGACY_* without
 * deleting olympus_accounting_* rows.
 */

/** Preferred public NAV series (finalized tips + labeled legacy estimates). */
export const ACCOUNTING_NAV_VIEW = 'public_accounting_nav_history' as const;

/** Pre-cutover public NAV (migration 050) — rollback target. */
export const LEGACY_PUBLIC_NAV_VIEW = 'public_nav_history' as const;

/** Public realized daily contribution (final tips only). */
export const PUBLIC_REALIZED_ATTRIBUTION_VIEW = 'public_daily_realized_attribution' as const;

/** Tip period status including incomplete/estimated/failed. */
export const PUBLIC_PERIOD_STATUS_VIEW = 'public_accounting_period_status' as const;

export type AccountingNavSource = 'finalized_accounting' | 'legacy_nav_history';
export type AccountingNavContract = 'finalized_accounting' | 'legacy_estimate';

export type AccountingNavRow = {
  date: string;
  nav: number;
  cash_pct: number | null;
  invested_pct: number | null;
  day_return_pct: number | null;
  source: AccountingNavSource | string;
  contract: AccountingNavContract | string;
};

/** Map a curated NAV row onto the legacy nav_history shape used by tearsheet builders. */
export function accountingNavToHistoryShape(row: AccountingNavRow): {
  date: string;
  nav: number;
  cash_pct: number | null;
  invested_pct: number | null;
  source: string;
  contract: string;
} {
  return {
    date: row.date,
    nav: row.nav,
    cash_pct: row.cash_pct,
    invested_pct: row.invested_pct,
    source: row.source,
    contract: row.contract,
  };
}

/**
 * Dominant series label for UI badges: finalized when any finalized row exists,
 * otherwise legacy. Never invents a mixed unlabeled value.
 */
export function navSeriesContractLabel(
  rows: Array<{ source?: string | null; contract?: string | null }>
): 'finalized_accounting' | 'legacy_estimate' | 'empty' {
  if (!rows.length) return 'empty';
  if (rows.some((r) => r.source === 'finalized_accounting' || r.contract === 'finalized_accounting')) {
    return 'finalized_accounting';
  }
  return 'legacy_estimate';
}

/**
 * Red-test helper: contribution fractions (as pct points) must sum to the shown
 * day return within a small absolute tolerance when both are present.
 */
export function contributionsSumToDayReturn(
  contributionPctPoints: number[],
  dayReturnPct: number,
  absTol = 1e-4
): boolean {
  const sum = contributionPctPoints.reduce((acc, v) => acc + v, 0);
  return Math.abs(sum - dayReturnPct) <= absTol;
}
