/**
 * Performance SSOT (#3580 / #3604) — Brief, Tearsheet, Ledger, and Portfolio share one
 * contracted series for NAV/returns and one committed-book date for positions.
 *
 * Live marks on Brief are an **opt-in overlay** (badged). They must never
 * silently replace the persisted accounting tip as a second truth.
 *
 * Canonical surfaces — see `TABLES.md` § Performance SSOT (metric-source matrix).
 */

import {
  computeLivePerformanceKpis,
  sinceInceptionPctFromNav,
} from '@digithings/web';
import {
  navSeriesContractLabel,
  type AccountingNavRow,
} from './accounting-views';
import { committedBookDate } from './dashboard-ssot';

/** Absolute tolerance (pp) for Brief persisted vs Tearsheet headline agreement. */
export const PERSISTED_KPI_TOLERANCE_PP = 0.05;

/**
 * Calendar-day threshold for metrics↔NAV divergence chrome.
 * Units: whole UTC calendar days between `YYYY-MM-DD` stamps. Symmetric.
 */
export const METRICS_DIVERGENCE_TOLERANCE_DAYS = 1;

/**
 * Maximum calendar-day gap for deriving day return from adjacent NAV rows
 * when `day_return_pct` is missing. Covers a weekend + one holiday; wider
 * gaps are finalizer holes, not a session return.
 */
export const MAX_DAY_RETURN_GAP_DAYS = 4;

export type NavContractBadge = 'finalized_accounting' | 'legacy_estimate' | 'empty';

export type InvestedDefinition =
  /** Tip row of `public_accounting_nav_history.invested_pct` — Brief + book envelope. */
  | 'accounting_nav_tip'
  /** Sum of non-CASH `positions.weight_pct` on the committed book date. */
  | 'book_weights'
  /** Stale/secondary — `portfolio_metrics.invested_pct` when NAV tip missing. */
  | 'portfolio_metrics'
  /** No invested source available — do not claim accounting tip. */
  | 'unavailable';

export interface PerformanceSsotMeta {
  /** Contract of the **displayed NAV tip**, not “any finalized row in history”. */
  navContract: NavContractBadge;
  /** Latest accounting NAV tip date. */
  navAsOf: string | null;
  /** Tip day return from the accounting series (null when flat/missing/gapped). */
  tipDayReturnPct: number | null;
  /** Tip invested % from accounting NAV (preferred invested definition). */
  tipInvestedPct: number | null;
  /** Tip cash % from accounting NAV when present. */
  tipCashPct: number | null;
  /** `portfolio_metrics.as_of_date` or `.date` when present — never overwritten with the NAV tip. */
  metricsAsOf: string | null;
  /**
   * Signed calendar-day divergence: `navAsOf − metricsAsOf`.
   * Positive = metrics behind the NAV tip; negative = NAV tip behind metrics.
   * Null when either stamp is missing.
   */
  metricsLagDays: number | null;
  /** True when |metricsLagDays| ≥ {@link METRICS_DIVERGENCE_TOLERANCE_DAYS}. */
  metricsLagging: boolean;
  /** Committed book date (`daily_snapshots.date` ∩ positions). */
  bookAsOf: string | null;
  /**
   * True when the open book is empty or any open-book position lacks
   * `metrics_as_of` — chrome must not imply marks were refreshed for that date.
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

/** Calendar-day difference (UTC date strings YYYY-MM-DD). later − earlier. */
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
 * Do not clamp >100 under an accounting-tip label — surface the tip value.
 */
export function resolveInvestedPct(args: {
  tipInvestedPct: number | null | undefined;
  bookWeightInvestedPct: number | null | undefined;
  metricsInvestedPct: number | null | undefined;
}): { investedPct: number | null; definition: InvestedDefinition } {
  if (args.tipInvestedPct != null && Number.isFinite(args.tipInvestedPct) && args.tipInvestedPct >= 0) {
    return { investedPct: args.tipInvestedPct, definition: 'accounting_nav_tip' };
  }
  if (
    args.bookWeightInvestedPct != null &&
    Number.isFinite(args.bookWeightInvestedPct) &&
    args.bookWeightInvestedPct >= 0
  ) {
    return {
      investedPct: args.bookWeightInvestedPct,
      definition: 'book_weights',
    };
  }
  if (
    args.metricsInvestedPct != null &&
    Number.isFinite(args.metricsInvestedPct) &&
    args.metricsInvestedPct >= 0
  ) {
    return {
      investedPct: args.metricsInvestedPct,
      definition: 'portfolio_metrics',
    };
  }
  return {
    investedPct: null,
    definition: 'unavailable',
  };
}

function derivedDayReturnPct(
  tip: { date: string; nav: number; day_return_pct?: number | null },
  prior: { date: string; nav: number } | null
): number | null {
  if (tip.day_return_pct != null && Number.isFinite(tip.day_return_pct)) {
    return tip.day_return_pct;
  }
  if (!prior || !(prior.nav > 0)) return null;
  const gap = calendarDaysBetween(prior.date, tip.date);
  if (gap == null || gap < 1 || gap > MAX_DAY_RETURN_GAP_DAYS) return null;
  return (tip.nav / prior.nav - 1) * 100;
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

  // Match Tearsheet `periodReturnPct`: need ≥2 finite NAV points for since-inception %.
  const sinceInceptionPct =
    sorted.length >= 2 && first && tip ? sinceInceptionPctFromNav(first.nav, tip.nav) : null;

  const invested = resolveInvestedPct({
    tipInvestedPct: tip?.invested_pct ?? null,
    bookWeightInvestedPct: opts.bookWeightInvestedPct ?? null,
    metricsInvestedPct: opts.metricsInvestedPct ?? null,
  });

  return {
    sinceInceptionPct,
    sinceInceptionStartDate: first?.date ?? null,
    dayReturnPct: tip ? derivedDayReturnPct(tip, prior) : null,
    navAsOf: tip?.date ?? null,
    investedPct: invested.investedPct,
    investedDefinition: invested.definition,
  };
}

/**
 * Excess / alpha / IR from persisted NAV + benchmark (no live overlay).
 * Sparse or late-starting (paginated) benchmark series still render when the
 * remaining overlapping daily pairs meet {@link MIN_OVERLAP_DAYS}.
 */
export function persistedInsightMetrics(
  nav: ReadonlyArray<{ date: string; nav: number }>,
  benchmarkHistory: ReadonlyArray<{ date: string; price: number }> | undefined
): {
  excessReturnPct: number | null;
  alphaPct: number | null;
  informationRatio: number | null;
} {
  const sorted = [...nav].filter((row) => finiteNav(row.nav));
  if (sorted.length < 2 || !benchmarkHistory?.length) {
    return { excessReturnPct: null, alphaPct: null, informationRatio: null };
  }
  const kpis = computeLivePerformanceKpis({
    positions: [],
    navHistory: sorted.map((row) => ({ date: row.date, nav: row.nav })),
    benchmarkHistory,
    benchmarkTicker: 'SPY',
  });
  return {
    excessReturnPct: kpis.excessReturnPct,
    alphaPct: kpis.alphaPct,
    informationRatio: kpis.informationRatio,
  };
}

export function buildPerformanceSsotMeta(args: {
  navRows: ReadonlyArray<
    Pick<AccountingNavRow, 'date' | 'source' | 'contract' | 'invested_pct' | 'day_return_pct'> & {
      nav?: number;
      cash_pct?: number | null;
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
  const prior = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  const tipDay =
    tip && finiteNav(tip.nav)
      ? derivedDayReturnPct(
          { date: tip.date, nav: tip.nav, day_return_pct: tip.day_return_pct },
          prior && finiteNav(prior.nav) ? { date: prior.date, nav: prior.nav } : null
        )
      : tip?.day_return_pct != null && Number.isFinite(tip.day_return_pct)
        ? tip.day_return_pct
        : null;

  return {
    navContract: navSeriesContractLabel(sorted),
    navAsOf,
    tipDayReturnPct: tipDay,
    tipInvestedPct:
      tip?.invested_pct != null && Number.isFinite(tip.invested_pct) ? tip.invested_pct : null,
    tipCashPct: tip?.cash_pct != null && Number.isFinite(tip.cash_pct) ? tip.cash_pct : null,
    metricsAsOf,
    metricsLagDays: lag,
    metricsLagging:
      lag != null && Math.abs(lag) >= METRICS_DIVERGENCE_TOLERANCE_DAYS,
    bookAsOf: committedBookDate(args.snapshotDate, args.positionDates),
    marksUnstamped:
      args.positionMetricsAsOf.length === 0 ||
      args.positionMetricsAsOf.some((v) => v == null || String(v).trim() === ''),
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

/**
 * Divergence chrome: equal-magnitude positive and negative lags both badge.
 * Positive days → metrics behind NAV; negative → NAV tip behind metrics.
 */
export function metricsDivergenceBadgeLabel(
  meta: Pick<PerformanceSsotMeta, 'metricsLagging' | 'metricsLagDays'>
): string | null {
  if (!meta.metricsLagging || meta.metricsLagDays == null) return null;
  if (meta.metricsLagDays > 0) return 'metrics lag';
  if (meta.metricsLagDays < 0) return 'nav lag';
  return null;
}

/** Lag / marks chrome — never imply fresh marks when unstamped. */
export function performanceFreshnessNote(meta: PerformanceSsotMeta): string | null {
  const parts: string[] = [];
  if (meta.navContract === 'legacy_estimate') {
    parts.push('NAV tip is legacy estimate (finalizer not producing tips)');
  }
  if (meta.metricsLagging && meta.metricsAsOf && meta.navAsOf && meta.metricsLagDays != null) {
    if (meta.metricsLagDays > 0) {
      parts.push(`metrics as of ${meta.metricsAsOf} (nav tip ${meta.navAsOf})`);
    } else {
      parts.push(`nav tip ${meta.navAsOf} (metrics as of ${meta.metricsAsOf})`);
    }
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
