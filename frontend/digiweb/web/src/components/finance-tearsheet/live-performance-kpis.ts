/**
 * Live portfolio performance KPIs — shared by digiquant.io landing and olympus Brief.
 *
 * Computes day return, since-inception, and excess vs benchmark from:
 *   - current holdings (weight_pct)
 *   - latest marks (live tick or last close)
 *   - accounting NAV history for prior-day / inception anchors
 *
 * Pure — no React, no I/O. Both consumers pass adapter-mapped inputs.
 */

export interface LiveKpiPosition {
  ticker: string;
  weightPct: number;
  /** Daily-close mark from the published book (`current_price`). */
  markPrice: number | null;
  /** Best available price: live tick when fresh, else mark. */
  effectivePrice: number | null;
  /** True when `effectivePrice` came from a non-stale live tick. */
  isLive: boolean;
  /** Book mark date (YYYY-MM-DD) from `metrics_as_of`. */
  metricsAsOf: string | null;
  /** Live quote calendar date (YYYY-MM-DD) when `isLive`. */
  livePriceDate: string | null;
}

export interface LiveKpiNavPoint {
  date: string;
  nav: number;
}

export interface LiveKpiBenchmarkPoint {
  date: string;
  price: number;
}

export interface LivePerformanceKpisInput {
  positions: readonly LiveKpiPosition[];
  navHistory: readonly LiveKpiNavPoint[];
  benchmarkHistory?: readonly LiveKpiBenchmarkPoint[];
  benchmarkTicker?: string | null;
}

export interface LivePerformanceKpis {
  /** Book revalued at effective prices, anchored on latest accounting NAV. */
  liveNav: number | null;
  /** Dimensionless move vs snapshot marks (percent points). */
  liveVsMarkPct: number;
  /** Price date used for KPI labels (YYYY-MM-DD). */
  priceAsOfDate: string | null;
  dayReturnPct: number | null;
  sinceInceptionPct: number | null;
  sinceInceptionStartDate: string | null;
  excessReturnPct: number | null;
  benchmarkTicker: string | null;
  /** Latest accounting NAV row date (book persistence). */
  bookNavDate: string | null;
}

const asDate = (iso: string | null | undefined): string | null => {
  if (!iso) return null;
  const d = iso.slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : null;
};

/** Weighted live move vs published marks — same formula as digiquant-web computeLiveTotal. */
export function computeLiveVsMarkPct(positions: readonly LiveKpiPosition[]): number {
  let move = 0;
  for (const p of positions) {
    const mark = p.markPrice;
    const price = p.effectivePrice;
    if (mark == null || mark <= 0 || price == null || price <= 0) continue;
    if (p.isLive) {
      move += (p.weightPct / 100) * (price / mark - 1);
    }
  }
  return move * 100;
}

/** Dominant price-as-of date across the book for KPI footnotes. */
export function derivePriceAsOfDate(positions: readonly LiveKpiPosition[]): string | null {
  let liveMax: string | null = null;
  let markMax: string | null = null;
  for (const p of positions) {
    if (p.isLive && p.livePriceDate) {
      if (!liveMax || p.livePriceDate > liveMax) liveMax = p.livePriceDate;
    }
    const markDate = asDate(p.metricsAsOf);
    if (markDate && (!markMax || markDate > markMax)) markMax = markDate;
  }
  return liveMax ?? markMax;
}

function pickBenchmarkPoints(
  history: readonly LiveKpiBenchmarkPoint[],
  startDate: string,
  endDate: string
): { start: LiveKpiBenchmarkPoint; end: LiveKpiBenchmarkPoint } | null {
  const sorted = [...history].sort((a, b) => a.date.localeCompare(b.date));
  const start = sorted.find((p) => p.date >= startDate);
  const end = [...sorted].reverse().find((p) => p.date <= endDate);
  if (!start || !end || start.date > end.date) return null;
  if (start.price <= 0 || end.price <= 0) return null;
  return { start, end };
}

/**
 * Compute live performance KPIs for landing + Brief scoreboard.
 *
 * Since-inception uses the base-100 paper index model when the first NAV is ~100:
 * `liveNav - 100`. Otherwise falls back to `(liveNav / firstNav - 1) * 100`.
 */
export function computeLivePerformanceKpis(input: LivePerformanceKpisInput): LivePerformanceKpis {
  const { positions, navHistory, benchmarkHistory, benchmarkTicker } = input;
  const sortedNav = [...navHistory].sort((a, b) => a.date.localeCompare(b.date));
  const latestNavRow = sortedNav.length > 0 ? sortedNav[sortedNav.length - 1] : null;
  const latestNav = latestNavRow?.nav ?? null;
  const liveVsMarkPct = computeLiveVsMarkPct(positions);
  const liveNav = latestNav == null ? null : latestNav * (1 + liveVsMarkPct / 100);
  const priceAsOfDate = derivePriceAsOfDate(positions);
  const bookNavDate = latestNavRow?.date ?? null;

  const priorNavRow = sortedNav.length >= 2 ? sortedNav[sortedNav.length - 2] : null;
  const dayReturnPct =
    liveNav != null && priorNavRow != null && priorNavRow.nav > 0
      ? (liveNav / priorNavRow.nav - 1) * 100
      : null;

  const firstNavRow = sortedNav.length > 0 ? sortedNav[0] : null;
  let sinceInceptionPct: number | null = null;
  if (liveNav != null && firstNavRow != null) {
    if (Math.abs(firstNavRow.nav - 100) < 0.01) {
      sinceInceptionPct = liveNav - 100;
    } else if (firstNavRow.nav > 0) {
      sinceInceptionPct = (liveNav / firstNavRow.nav - 1) * 100;
    }
  }

  let excessReturnPct: number | null = null;
  let benchTickerOut: string | null = benchmarkTicker ?? null;
  if (
    liveNav != null &&
    firstNavRow != null &&
    firstNavRow.nav > 0 &&
    benchmarkHistory?.length &&
    benchTickerOut
  ) {
    const endDate = priceAsOfDate ?? bookNavDate ?? latestNavRow?.date ?? null;
    const startDate = firstNavRow.date;
    if (endDate) {
      const aligned = pickBenchmarkPoints(benchmarkHistory, startDate, endDate);
      if (aligned) {
        const portPct = (liveNav / firstNavRow.nav - 1) * 100;
        const benchPct = (aligned.end.price / aligned.start.price - 1) * 100;
        excessReturnPct = portPct - benchPct;
      }
    }
  }

  return {
    liveNav,
    liveVsMarkPct,
    priceAsOfDate,
    dayReturnPct,
    sinceInceptionPct,
    sinceInceptionStartDate: firstNavRow?.date ?? null,
    excessReturnPct,
    benchmarkTicker: benchTickerOut,
    bookNavDate,
  };
}
