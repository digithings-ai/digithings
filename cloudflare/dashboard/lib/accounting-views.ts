/**
 * Curated dashboard / digiquant.io accounting read surface (#2599 / Task 3.4).
 *
 * Prefer these view names in adapters. Rollback = repoint to LEGACY_* without
 * deleting dashboard_accounting_* rows.
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
  /**
   * True on the first row after a source flip (migration 123 / #3767).
   * Charts must break the line at a seam — never draw a continuous return
   * across legacy estimates and finalized accounting.
   */
  series_seam?: boolean | null;
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
 * Provenance of one NAV row. Unlabeled rows are estimates — never finalized.
 */
export function navRowContractLabel(row: {
  source?: string | null;
  contract?: string | null;
}): 'finalized_accounting' | 'legacy_estimate' {
  if (row.contract === 'finalized_accounting' || row.source === 'finalized_accounting') {
    return 'finalized_accounting';
  }
  return 'legacy_estimate';
}

/**
 * Badge for the displayed NAV tip (latest dated row). Historical finalized
 * rows must not relabel a legacy-estimate tip as finalized accounting.
 */
export function navSeriesContractLabel(
  rows: Array<{ date?: string | null; source?: string | null; contract?: string | null }>
): 'finalized_accounting' | 'legacy_estimate' | 'empty' {
  if (!rows.length) return 'empty';
  const dated = rows.filter((r) => typeof r.date === 'string' && r.date.length > 0);
  const tip = dated.length
    ? [...dated].sort((a, b) => String(a.date).localeCompare(String(b.date))).at(-1)
    : rows[rows.length - 1];
  return navRowContractLabel(tip!);
}

/**
 * True when a NAV row sits on a legacy↔finalized seam (migration 123 / #3767).
 * Accepts the explicit `series_seam` flag or a detected source flip against
 * the previous calendar row (for readers on an unmigrated view).
 */
export function isNavSeriesSeam(
  row: { series_seam?: boolean | null; source?: string | null },
  prevSource?: string | null
): boolean {
  if (row.series_seam === true) return true;
  if (prevSource == null) return false;
  const source = row.source ?? null;
  return source != null && prevSource != null && source !== prevSource;
}

/**
 * Dates where the stitched NAV series flips source (#3767). Charts break the
 * line at these dates instead of drawing a phantom return across two series.
 */
export function findNavSeriesSeams(
  rows: ReadonlyArray<{ date: string; source?: string | null; series_seam?: boolean | null }>
): string[] {
  const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  const seams: string[] = [];
  let prevSource: string | null | undefined;
  for (const row of sorted) {
    if (prevSource !== undefined && isNavSeriesSeam(row, prevSource)) {
      seams.push(row.date);
    }
    prevSource = row.source ?? null;
  }
  return seams;
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

/** True when PostgREST cannot find the relation (unapplied migration / schema cache). */
export function isMissingPublicRelationError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const e = error as { code?: string; message?: string };
  if (e.code === 'PGRST205') return true;
  const msg = typeof e.message === 'string' ? e.message.toLowerCase() : '';
  return msg.includes('schema cache') || msg.includes('could not find the table');
}

/**
 * Fail-closed contract error for the curated public NAV series (#2599 / #3029).
 * Callers must surface this — never swallow into an empty success tearsheet/book.
 */
export class AccountingNavContractError extends Error {
  readonly code = 'accounting_nav_contract' as const;
  readonly view = ACCOUNTING_NAV_VIEW;
  readonly causeError: unknown;

  constructor(causeError: unknown) {
    const detail =
      causeError && typeof causeError === 'object' && 'message' in causeError
        ? String((causeError as { message: unknown }).message)
        : causeError instanceof Error
          ? causeError.message
          : String(causeError ?? 'unknown error');
    const missing = isMissingPublicRelationError(causeError);
    super(
      missing
        ? `Accounting NAV contract failed: view "${ACCOUNTING_NAV_VIEW}" is missing ` +
            `(PostgREST PGRST205). Apply digiquant migrations 072–074 on the core ` +
            `Supabase project, then reload. Detail: ${detail}`
        : `Accounting NAV contract failed reading "${ACCOUNTING_NAV_VIEW}": ${detail}`
    );
    this.name = 'AccountingNavContractError';
    this.causeError = causeError;
  }
}

/** Throw when a public accounting NAV query did not succeed. */
export function assertAccountingNavQueryOk(error: unknown): void {
  if (error) throw new AccountingNavContractError(error);
}
