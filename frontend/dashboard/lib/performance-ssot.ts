/**
 * Performance SSOT (#3580) — Brief, Tearsheet, Ledger, and Portfolio share one
 * contracted series for NAV/returns and one committed-book date for positions.
 *
 * Live marks on Brief are an **opt-in overlay** (badged). They must never
 * silently replace the persisted accounting tip as a second truth.
 *
 * Canonical surfaces — see `TABLES.md` § Performance SSOT.
 */

import {
  navSeriesContractLabel,
  type AccountingNavRow,
} from './accounting-views';
import { committedBookDate } from './dashboard-ssot';
import { sinceInceptionPctFromNav } from '@digithings/web';

/** Absolute tolerance (pp) for Brief persisted vs Tearsheet headline agreement. */
export const PERSISTED_KPI_TOLERANCE_PP = 0.05;

export type NavContractBadge = 'finalized_accounting' | 'legacy_estimate' | 'empty';

export type InvestedDefinition =
  /** Tip row of `public_accounting_nav_history.invested_pct` — Brief + book envelope. */
  | 'accounting_nav_tip'
  /** Sum of non-CASH `positions.weight_pct` on the committed book date. */
  | 'book_weights'
  /** Stale/secondary — `portfolio_metrics.invested_pct` when NAV tip missing. */
  | 'portfolio_metrics';

export interface PerformanceSsotMeta {
  /** Dominant series contract for the NAV chart / tip. */
  navContract: NavContractBadge;
  /** Latest accounting NAV tip date. */
  navAsOf: string | null;
  /** Tip day return from the accounting series (null when flat/missing). */
  tipDayReturnPct: number | null;
  /** Tip invested % from accounting NAV (preferred invested definition). */
  tipInvestedPct: number | null;
  /** `portfolio_metrics.as_of_date` or `.date` when present. */
  metricsAsOf: string | null;
  /** Calendar days metrics lag behind the NAV tip (null when either missing). */
  metricsLagDays: number | null;
  /** True when metrics are behind the NAV tip by ≥1 calendar day. */
  metricsLagging: boolean;
  /** Committed book date (`daily_snapshots.date` ∩ positions). */
  bookAsOf: string | null;
  /**
   * True when any open-book position lacks `metrics_as_of` — chrome must not
   * imply marks were refreshed for that date.
   */
  marksUnstamped: boolean;
  investedDefinition: InvestedDefinition;
}

export interface PersistedPerformanceHeadlines {
  sinceInceptionPct: number | null;
  sinceInceptionStartDate: string | null;
  dayReturnPct: number | null;
  navAsOf: string | null;
  investedPct: number | null;
  investedDefinition: InvestedDefinition;
}

function finiteNav(nav: number | null | undefined): nav is number {
  return nav != null && Number.isFinite(nav) && nav > 0;
}

/** Calendar-day lag (UTC date strings YYYY-MM-DD). */
export function calendarDaysBetween(earlier: string, later: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(earlier) || !/^\d{4}-\d{2}-\d{2}$/.test(later)) {
    return null;
  }
  const a = Date.UTC(+earlier.slice(0, 4), +earlier.slice(5, 7) - 1, +earlier.slice(8, 10));
  const b = Date.UTC(+later.slice(0, 4), +later.slice(5, 7) - 1, +later.slice(8, 10));
  return Math.round((b - a) / 86_400_000);
}

/**
 * Prefer accounting NAV tip invested %; else book weights; else metrics.
 * Never silently mix live weights with book weights for the Invested tile.
 */
export function resolveInvestedPct(args: {
  tipInvestedPct: number | null | undefined;
  bookWeightInvestedPct: number | null | undefined;
  metricsInvestedPct: number | null | undefined;
}): { investedPct: number | null; definition: InvestedDefinition } {
  if (args.tipInvestedPct != null && Number.isFinite(args.tipInvestedPct) && args.tipInvestedPct >= 0) {
    return { investedPct: Math.min(100, args.tipInvestedPct), definition: 'accounting_nav_tip' };
  }
  if (
    args.bookWeightInvestedPct != null &&
    Number.isFinite(args.bookWeightInvestedPct) &&
    args.bookWeightInvestedPct >= 0
  ) {
    return {
      investedPct: Math.min(100, args.bookWeightInvestedPct),
      definition: 'book_weights',
    };
  }
  if (
    args.metricsInvestedPct != null &&
    Number.isFinite(args.metricsInvestedPct) &&
    args.metricsInvestedPct >= 0
  ) {
    return {
      investedPct: Math.min(100, args.metricsInvestedPct),
      definition: 'portfolio_metrics',
    };
  }
  return { investedPct: null, definition: 'accounting_nav_tip' };
}

/** Headline KPIs from the persisted accounting NAV series (no live overlay). */
export function persistedHeadlinesFromNav(
  nav: ReadonlyArray<{
    date: string;
    nav: number;
    invested_pct?: number | null;
    day_return_pct?: number | null;
  }>,
  opts: {
    bookWeightInvestedPct?: number | null;
    metricsInvestedPct?: number | null;
  } = {}
): PersistedPerformanceHeadlines {
  const sorted = [...nav]
    .filter((row) => finiteNav(row.nav))
    .sort((a, b) => a.date.localeCompare(b.date));
  const first = sorted[0] ?? null;
  const tip = sorted.at(-1) ?? null;
  const prior = sorted.length >= 2 ? sorted[sorted.length - 2] : null;

  const sinceInceptionPct =
    first && tip ? sinceInceptionPctFromNav(first.nav, tip.nav) : null;

  let dayReturnPct: number | null = null;
  if (tip?.day_return_pct != null && Number.isFinite(tip.day_return_pct)) {
    dayReturnPct = tip.day_return_pct;
  } else if (tip && prior && prior.nav > 0) {
    dayReturnPct = (tip.nav / prior.nav - 1) * 100;
  }

  const invested = resolveInvestedPct({
    tipInvestedPct: tip?.invested_pct ?? null,
    bookWeightInvestedPct: opts.bookWeightInvestedPct ?? null,
    metricsInvestedPct: opts.metricsInvestedPct ?? null,
  });

  return {
    sinceInceptionPct,
    sinceInceptionStartDate: first?.date ?? null,
    dayReturnPct,
    navAsOf: tip?.date ?? null,
    investedPct: invested.investedPct,
    investedDefinition: invested.definition,
  };
}

export function buildPerformanceSsotMeta(args: {
  navRows: ReadonlyArray<
    Pick<AccountingNavRow, 'date' | 'source' | 'contract' | 'invested_pct' | 'day_return_pct'> & {
      nav?: number;
    }
  >;
  metricsAsOf: string | null | undefined;
  snapshotDate: string | null | undefined;
  positionDates: readonly string[];
  /** Per open-book row `metrics_as_of` (null/undefined = unstamped). */
  positionMetricsAsOf: readonly (string | null | undefined)[];
  bookWeightInvestedPct?: number | null;
  metricsInvestedPct?: number | null;
}): PerformanceSsotMeta {
  const sorted = [...args.navRows].sort((a, b) => a.date.localeCompare(b.date));
  const tip = sorted.at(-1) ?? null;
  const navAsOf = tip?.date ?? null;
  const metricsAsOf = args.metricsAsOf?.slice(0, 10) || null;
  const lag =
    navAsOf && metricsAsOf ? calendarDaysBetween(metricsAsOf, navAsOf) : null;
  const invested = resolveInvestedPct({
    tipInvestedPct: tip?.invested_pct ?? null,
    bookWeightInvestedPct: args.bookWeightInvestedPct ?? null,
    metricsInvestedPct: args.metricsInvestedPct ?? null,
  });

  return {
    navContract: navSeriesContractLabel(sorted),
    navAsOf,
    tipDayReturnPct:
      tip?.day_return_pct != null && Number.isFinite(tip.day_return_pct)
        ? tip.day_return_pct
        : null,
    tipInvestedPct:
      tip?.invested_pct != null && Number.isFinite(tip.invested_pct) ? tip.invested_pct : null,
    metricsAsOf,
    metricsLagDays: lag != null && lag > 0 ? lag : lag === 0 ? 0 : null,
    metricsLagging: lag != null && lag >= 1,
    bookAsOf: committedBookDate(args.snapshotDate, args.positionDates),
    marksUnstamped: args.positionMetricsAsOf.some((v) => v == null || String(v).trim() === ''),
    investedDefinition: invested.definition,
  };
}

/** True when Brief persisted since-% and Tearsheet headline agree within tolerance. */
export function persistedHeadlinesAgree(
  briefSincePct: number | null,
  tearsheetNetReturnPct: number | null,
  tolerancePp = PERSISTED_KPI_TOLERANCE_PP
): boolean {
  if (briefSincePct == null || tearsheetNetReturnPct == null) return false;
  return Math.abs(briefSincePct - tearsheetNetReturnPct) <= tolerancePp;
}

/** Operator-facing contract badge copy (lowercase digi product names only). */
export function navContractBadgeLabel(contract: NavContractBadge): string {
  if (contract === 'finalized_accounting') return 'finalized accounting';
  if (contract === 'legacy_estimate') return 'legacy estimate';
  return 'no nav series';
}

/** Lag / marks chrome — never imply fresh marks when unstamped. */
export function performanceFreshnessNote(meta: PerformanceSsotMeta): string | null {
  const parts: string[] = [];
  if (meta.navContract === 'legacy_estimate') {
    parts.push('NAV series is legacy estimate (finalizer not producing tips)');
  }
  if (meta.metricsLagging && meta.metricsAsOf && meta.navAsOf) {
    parts.push(`metrics as of ${meta.metricsAsOf} (nav tip ${meta.navAsOf})`);
  }
  if (meta.marksUnstamped) {
    parts.push('position marks unstamped (metrics_as_of null)');
  }
  return parts.length ? parts.join(' · ') : null;
}

/** Live overlay is active only when marks moved the index vs the book tip. */
export function isLiveMarksOverlay(liveVsMarkPct: number | null | undefined): boolean {
  return liveVsMarkPct != null && Math.abs(liveVsMarkPct) > 1e-9;
}
