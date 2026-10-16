/**
 * Live portfolio performance KPIs — shared by digiquant.io landing, dashboard Brief,
 * and (via series helpers) the Performance tearsheet.
 *
 * Computes percentage returns (day, since inception, vs benchmark) from:
 *   - current holdings (weight_pct)
 *   - latest marks (live tick or last close)
 *   - accounting NAV history for prior-day / inception anchors
 *
 * NAV is a paper base-100 index used only as an internal valuation anchor — never
 * the primary display. Pure — no React, no I/O.
 *
 * Insight metrics (documented definitions):
 *   - excess / relative return: Rp − Rb over the aligned window (percentage points)
 *   - relative gain: alias of excess return (same window)
 *   - alpha: single-factor Jensen alpha = Rp − β·Rb, with β from overlapping daily
 *     returns (OLS). Null when fewer than {@link MIN_OVERLAP_DAYS} pairs — we do
 *     not invent CAPM alpha from endpoints alone.
 *   - information ratio: mean(daily excess) / sampleStd(daily excess) · √252.
 *     Null when overlap is too short or tracking error is ~0.
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
  /**
   * Accounting day return for the row (percent points). Preferred step for the
   * continuity index; absent on rows that predate the accounting contract.
   */
  day_return_pct?: number | null;
  /** Row source (`legacy_nav_history` / `finalized_accounting`). */
  source?: string | null;
  /** True on the first row after a legacy↔finalized flip. */
  series_seam?: boolean | null;
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
  /**
   * Live-marked base-100 index level (internal). Prefer returning % metrics
   * to UI — expose only when a footnote needs the raw index.
   */
  liveNav: number | null;
  /** Dimensionless move vs snapshot marks (percent points). */
  liveVsMarkPct: number;
  /** Price date used for KPI labels (YYYY-MM-DD). */
  priceAsOfDate: string | null;
  dayReturnPct: number | null;
  sinceInceptionPct: number | null;
  sinceInceptionStartDate: string | null;
  /** Portfolio total return over the aligned benchmark window (pp). */
  portfolioReturnPct: number | null;
  /** Benchmark total return over the same window (pp). */
  benchmarkReturnPct: number | null;
  /** Rp − Rb (percentage points). Primary relative metric. */
  excessReturnPct: number | null;
  /** Alias of {@link excessReturnPct} — same aligned window. */
  relativeGainPct: number | null;
  /**
   * Jensen alpha = Rp − β·Rb (percentage points on the total-return window),
   * with β from overlapping daily returns. Null when overlap is insufficient.
   */
  alphaPct: number | null;
  /**
   * Annualized information ratio from overlapping daily active returns.
   * Null when overlap is insufficient or tracking error ≈ 0.
   */
  informationRatio: number | null;
  benchmarkTicker: string | null;
  /** Latest accounting NAV row date (book persistence). */
  bookNavDate: string | null;
}

/** Minimum overlapping daily pairs for beta / IR (honest sample, not endpoints). */
export const MIN_OVERLAP_DAYS = 20;

const TRADING_DAYS = 252;
const BASE100_EPS = 0.01;

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

/** Mirror of `CONTINUITY_MAX_STEP_PCT` in `apps/dashboard-api/src/ssot.ts`. */
const CONTINUITY_MAX_STEP_PCT = 25;

/** Mirror of `isNavSeriesSeam` in `apps/dashboard-api/src/ssot.ts`. */
function isNavSeriesSeam(
  row: LiveKpiNavPoint,
  prevSource: string | null | undefined,
): boolean {
  if (row.series_seam === true) return true;
  if (prevSource == null) return false;
  const source = row.source ?? null;
  return source != null && prevSource != null && source !== prevSource;
}

/**
 * One chain step (percent points). Prefers the row's own day return, clamps a
 * move that cannot be performance, and returns 0 across a source seam — so a
 * rebasing/flow level jump never enters the index.
 */
function continuityStepPct(row: LiveKpiNavPoint, previous: LiveKpiNavPoint | undefined): number {
  const daily = row.day_return_pct;
  if (daily != null && Number.isFinite(daily)) {
    return Math.abs(daily) <= CONTINUITY_MAX_STEP_PCT ? daily : 0;
  }
  if (!isNavSeriesSeam(row, previous?.source ?? null) && previous != null && previous.nav > 0) {
    const level = (row.nav / previous.nav - 1) * 100;
    if (Number.isFinite(level) && Math.abs(level) <= CONTINUITY_MAX_STEP_PCT) return level;
  }
  return 0;
}

/**
 * Base-100 continuity index over the accounting rows — the SAME chain `/brief`
 * plots. Mirror of `buildContinuityNavSeries` (apps/dashboard-api/src/ssot.ts),
 * without the 2dp rounding that module applies for display.
 *
 * Accounting NAV levels carry flows and rebasing that never appear in
 * `day_return_pct`; dividing NAV by 100 counts those level jumps as returns.
 */
export function continuityIndexSeries(rows: readonly LiveKpiNavPoint[]): LiveKpiNavPoint[] {
  const sorted = [...rows]
    .filter((r) => Number.isFinite(r.nav) && r.nav > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
  if (sorted.length === 0) return [];
  const out: LiveKpiNavPoint[] = [{ date: sorted[0].date, nav: 100 }];
  let index = 100;
  for (let i = 1; i < sorted.length; i += 1) {
    index *= 1 + continuityStepPct(sorted[i], sorted[i - 1]) / 100;
    out.push({ date: sorted[i].date, nav: index });
  }
  return out;
}

/**
 * Since-inception % from a base-100 (or arbitrary) NAV level.
 * When the series seeds at ~100, this equals `lastNav - 100`.
 */
export function sinceInceptionPctFromNav(firstNav: number, lastNav: number): number | null {
  if (!(firstNav > 0) || !Number.isFinite(lastNav)) return null;
  return (lastNav / firstNav - 1) * 100;
}

/**
 * Invariant: when the book seeds at base 100, since-inception sign must match
 * whether the live index is above or below 100. Returns false on disagreement.
 */
export function inceptionSignAgreesWithBase100(
  firstNav: number,
  lastNav: number,
  sincePct: number
): boolean {
  if (Math.abs(firstNav - 100) >= BASE100_EPS) return true;
  if (Math.abs(lastNav - 100) < BASE100_EPS) return Math.abs(sincePct) < BASE100_EPS;
  if (lastNav > 100) return sincePct > 0;
  if (lastNav < 100) return sincePct < 0;
  return true;
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

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

function sampleStd(xs: number[]): number {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  const v = xs.reduce((a, x) => a + (x - m) ** 2, 0) / (xs.length - 1);
  return Math.sqrt(v);
}

/**
 * Align NAV and benchmark to common dates (as-of forward fill on benchmark),
 * then emit overlapping daily simple returns for both series.
 */
export function overlappingDailyReturns(
  navHistory: readonly LiveKpiNavPoint[],
  benchmarkHistory: readonly LiveKpiBenchmarkPoint[]
): { port: number[]; bench: number[] } {
  const nav = [...navHistory].sort((a, b) => a.date.localeCompare(b.date));
  const bench = [...benchmarkHistory].sort((a, b) => a.date.localeCompare(b.date));
  if (nav.length < 2 || bench.length < 2) return { port: [], bench: [] };

  const port: number[] = [];
  const benchRets: number[] = [];
  let bi = -1;
  let priorNav: number | null = null;
  let priorBench: number | null = null;

  for (const row of nav) {
    while (bi + 1 < bench.length && bench[bi + 1].date <= row.date) bi += 1;
    const bPrice = bi >= 0 ? bench[bi].price : null;
    if (priorNav != null && priorNav > 0 && priorBench != null && priorBench > 0 && bPrice != null && bPrice > 0) {
      port.push(row.nav / priorNav - 1);
      benchRets.push(bPrice / priorBench - 1);
    }
    priorNav = row.nav;
    if (bPrice != null && bPrice > 0) priorBench = bPrice;
  }
  return { port, bench: benchRets };
}

/**
 * OLS beta of portfolio daily returns on benchmark daily returns.
 * Null when sample is shorter than {@link MIN_OVERLAP_DAYS}.
 */
export function olsBeta(portDaily: readonly number[], benchDaily: readonly number[]): number | null {
  const n = Math.min(portDaily.length, benchDaily.length);
  if (n < MIN_OVERLAP_DAYS) return null;
  const p = portDaily.slice(0, n);
  const b = benchDaily.slice(0, n);
  const mp = mean(p);
  const mb = mean(b);
  let cov = 0;
  let varB = 0;
  for (let i = 0; i < n; i++) {
    const dp = p[i] - mp;
    const db = b[i] - mb;
    cov += dp * db;
    varB += db * db;
  }
  if (varB < 1e-18) return null;
  return cov / varB;
}

/**
 * Annualized information ratio from overlapping daily active returns.
 * IR = mean(Rp−Rb) / std(Rp−Rb) · √252.
 */
export function informationRatioFromDaily(
  portDaily: readonly number[],
  benchDaily: readonly number[]
): number | null {
  const n = Math.min(portDaily.length, benchDaily.length);
  if (n < MIN_OVERLAP_DAYS) return null;
  const active: number[] = [];
  for (let i = 0; i < n; i++) active.push(portDaily[i] - benchDaily[i]);
  const te = sampleStd(active);
  if (te < 1e-12) return null;
  return (mean(active) / te) * Math.sqrt(TRADING_DAYS);
}

/**
 * Build the NAV series used for overlapping daily returns when a live tip
 * may sit on a later calendar day than the last accounting row.
 *
 * Keep every accounting observation and append the live tip when `endDate`
 * is strictly after the book — dropping the last accounting row can drop a
 * valid overlap pair below {@link MIN_OVERLAP_DAYS}.
 */
export function navHistoryForLiveOverlap(
  sortedNav: readonly LiveKpiNavPoint[],
  endDate: string,
  liveNav: number
): LiveKpiNavPoint[] {
  const last = sortedNav.at(-1);
  if (!last) return [{ date: endDate, nav: liveNav }];
  if (endDate === last.date) {
    return [...sortedNav.slice(0, -1), { date: endDate, nav: liveNav }];
  }
  if (endDate > last.date) {
    return [...sortedNav, { date: endDate, nav: liveNav }];
  }
  return [...sortedNav];
}

/**
 * Day-return anchor: when price marks are on a calendar day after the latest
 * accounting NAV row, the day baseline is that latest close. When marks share
 * the book date (post-EOD), baseline is the prior NAV row so the printed day
 * return still reflects the last completed session.
 */
export function dayReturnAnchorNav(
  sortedNav: readonly LiveKpiNavPoint[],
  priceAsOfDate: string | null
): number | null {
  if (sortedNav.length === 0) return null;
  const latest = sortedNav[sortedNav.length - 1];
  const prior = sortedNav.length >= 2 ? sortedNav[sortedNav.length - 2] : null;
  if (priceAsOfDate && latest.date && priceAsOfDate > latest.date) {
    return latest.nav > 0 ? latest.nav : null;
  }
  if (prior && prior.nav > 0) return prior.nav;
  return latest.nav > 0 ? latest.nav : null;
}

/**
 * Compute live performance KPIs for landing + Brief scoreboard.
 *
 * Since-inception always uses `(liveNav / firstNav − 1) · 100` so the sign
 * cannot disagree with a base-100 index level.
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

  const anchor = dayReturnAnchorNav(sortedNav, priceAsOfDate);
  const dayReturnPct =
    liveNav != null && anchor != null && anchor > 0 ? (liveNav / anchor - 1) * 100 : null;

  const firstNavRow = sortedNav.length > 0 ? sortedNav[0] : null;
  // Since-inception is the SAME base-100 continuity index `/brief` plots — never
  // `nav / 100`. Accounting NAV levels carry flows and rebasing that never appear
  // in `day_return_pct`, so a raw-level ratio reports non-performance level jumps
  // as returns. The live move is applied to the INDEX tip, not the NAV tip.
  const continuity = continuityIndexSeries(sortedNav);
  const indexTip = continuity.length > 0 ? continuity[continuity.length - 1].nav : null;
  const liveIndex = indexTip == null ? null : indexTip * (1 + liveVsMarkPct / 100);
  const sinceInceptionPct =
    liveIndex != null && continuity.length >= 2
      ? sinceInceptionPctFromNav(continuity[0].nav, liveIndex)
      : null;

  let portfolioReturnPct: number | null = sinceInceptionPct;
  let benchmarkReturnPct: number | null = null;
  let excessReturnPct: number | null = null;
  let alphaPct: number | null = null;
  let informationRatio: number | null = null;
  const benchTickerOut: string | null = benchmarkTicker ?? null;

  if (
    liveNav != null &&
    sinceInceptionPct != null &&
    firstNavRow != null &&
    benchmarkHistory?.length &&
    benchTickerOut
  ) {
    // Prefer live mark date only when it is *after* the book row; a stale
    // metrics_as_of earlier than bookNavDate must not shrink the window while
    // portfolio return still uses the later liveNav.
    const endDate =
      priceAsOfDate && bookNavDate && priceAsOfDate > bookNavDate
        ? priceAsOfDate
        : (bookNavDate ?? priceAsOfDate ?? latestNavRow?.date ?? null);
    const startDate = firstNavRow.date;
    if (endDate) {
      const aligned = pickBenchmarkPoints(benchmarkHistory, startDate, endDate);
      if (aligned) {
        // Portfolio leg is the index-based since-inception — the same number
        // `/brief` reports, so the two can never disagree. The benchmark leg
        // stays level-based: a price index carries no flows.
        portfolioReturnPct = sinceInceptionPct;
        benchmarkReturnPct = (aligned.end.price / aligned.start.price - 1) * 100;
        excessReturnPct = portfolioReturnPct - benchmarkReturnPct;

        const { port, bench } = overlappingDailyReturns(
          navHistoryForLiveOverlap(sortedNav, endDate, liveNav),
          benchmarkHistory
        );
        const beta = olsBeta(port, bench);
        if (beta != null && portfolioReturnPct != null && benchmarkReturnPct != null) {
          // Jensen alpha on the total-return window using daily-estimated β.
          alphaPct = portfolioReturnPct - beta * benchmarkReturnPct;
        }
        informationRatio = informationRatioFromDaily(port, bench);
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
    portfolioReturnPct,
    benchmarkReturnPct,
    excessReturnPct,
    relativeGainPct: excessReturnPct,
    alphaPct,
    informationRatio,
    benchmarkTicker: benchTickerOut,
    bookNavDate,
  };
}

/**
 * Relative / risk-adjusted metrics from aligned cumulative return series
 * (Performance tearsheet). Series are rebased to 0% at the first point.
 */
export function relativeMetricsFromReturnSeries(
  portfolioReturnPct: number | null,
  benchmarkReturnPct: number | null,
  portfolioCumulativePct: readonly number[],
  benchmarkCumulativePct: readonly number[]
): {
  excessReturnPct: number | null;
  relativeGainPct: number | null;
  alphaPct: number | null;
  informationRatio: number | null;
} {
  const excessReturnPct =
    portfolioReturnPct != null && benchmarkReturnPct != null
      ? portfolioReturnPct - benchmarkReturnPct
      : null;

  const toDaily = (cum: readonly number[]): number[] => {
    const out: number[] = [];
    for (let i = 1; i < cum.length; i++) {
      const prev = 1 + cum[i - 1] / 100;
      const cur = 1 + cum[i] / 100;
      if (prev > 0) out.push(cur / prev - 1);
    }
    return out;
  };

  const portDaily = toDaily(portfolioCumulativePct);
  const benchDaily = toDaily(benchmarkCumulativePct);
  const beta = olsBeta(portDaily, benchDaily);
  const alphaPct =
    beta != null && portfolioReturnPct != null && benchmarkReturnPct != null
      ? portfolioReturnPct - beta * benchmarkReturnPct
      : null;

  return {
    excessReturnPct,
    relativeGainPct: excessReturnPct,
    alphaPct,
    informationRatio: informationRatioFromDaily(portDaily, benchDaily),
  };
}
