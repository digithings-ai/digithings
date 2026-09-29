/**
 * dashboard-api shared performance kernel (slice 0004).
 *
 * Pure, dependency-free ports of the client-side derivations in
 * `apps/dashboard/lib/performance-ssot.ts`, `apps/dashboard/lib/accounting-views.ts`,
 * `apps/dashboard/lib/dashboard-ssot.ts` (committedBookDate),
 * `apps/dashboard/lib/benchmark-tickers.ts`, `apps/dashboard/lib/brief-book-event.ts`,
 * `apps/dashboard/lib/observability-queries.ts` (continuity series + benchmark
 * alignment) and `packages/ui` live-performance-kpis math.
 *
 * The worker serves snapshots only; no subscriptions, no realtime lane here.
 * All digi product names stay lowercase.
 */

/** Absolute tolerance (pp) for Brief persisted vs Tearsheet headline agreement. */
export const PERSISTED_KPI_TOLERANCE_PP = 0.05;

/** Whole-UTC-day tolerance before metrics↔NAV divergence gets a badge. */
export const METRICS_DIVERGENCE_TOLERANCE_DAYS = 1;

/** Max calendar-day gap for deriving a day return from adjacent NAV rows. */
export const MAX_DAY_RETURN_GAP_DAYS = 4;

/** Min overlapping daily pairs for beta / alpha / IR. Null below, never invented. */
export const MIN_OVERLAP_DAYS = 20;

/** A daily step beyond this is a basis/funding artifact, not a return. */
export const CONTINUITY_MAX_STEP_PCT = 25;

/** Gaps up to this many calendar days forward-fill flat (weekend/holiday). */
export const CONTINUITY_MAX_FILL_DAYS = 4;

const TRADING_DAYS = 252;

/** Default relative-performance benchmark for Brief + tearsheet. */
export const DEFAULT_BRIEF_BENCHMARK_TICKER = 'SPY';

export const DASHBOARD_BENCHMARK_TICKERS = [
  DEFAULT_BRIEF_BENCHMARK_TICKER,
  'QQQ',
  'DIA',
  'IWM',
  'VTI',
  'EEM',
  'TLT',
  'IEF',
  'AGG',
  'HYG',
  'GLD',
  'SLV',
  'USO',
  'UUP',
  'IBIT',
  'BITO',
  'EFA',
] as const;

export type NavContractBadge = 'finalized_accounting' | 'legacy_estimate' | 'empty';

export type InvestedDefinition =
  | 'accounting_nav_tip'
  | 'book_weights'
  | 'portfolio_metrics'
  | 'unavailable';

export interface NavRowInput {
  date: string;
  nav: number;
  invested_pct?: number | null;
  cash_pct?: number | null;
  day_return_pct?: number | null;
  source?: string | null;
  contract?: string | null;
  series_seam?: boolean | null;
}

/** Round to 6dp — matches the dashboard `roundPct` helper exactly. */
export function roundPct(value: number): number {
  return Math.round(value * 1_000_000) / 1_000_000;
}

function finiteNav(nav: number | null | undefined): nav is number {
  return nav != null && Number.isFinite(nav) && nav > 0;
}

/** Calendar-day difference (UTC `YYYY-MM-DD`). later − earlier; null when malformed. */
export function calendarDaysBetween(earlier: string, later: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(earlier) || !/^\d{4}-\d{2}-\d{2}$/.test(later)) {
    return null;
  }
  const a = Date.UTC(+earlier.slice(0, 4), +earlier.slice(5, 7) - 1, +earlier.slice(8, 10));
  const b = Date.UTC(+later.slice(0, 4), +later.slice(5, 7) - 1, +later.slice(8, 10));
  return Math.round((b - a) / 86_400_000);
}

export function nextIsoDate(date: string): string {
  const [year, month, day] = date.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10);
}

/**
 * Committed book date: latest position date on or before the snapshot date.
 * Never substitute a newer position date as "committed".
 */
export function committedBookDate(
  snapshotDate: string | null | undefined,
  positionDates: readonly string[],
): string | null {
  if (!snapshotDate) return null;
  let best: string | null = null;
  for (const date of positionDates) {
    if (date <= snapshotDate && (best == null || date > best)) best = date;
  }
  return best;
}

/**
 * Prefer the accounting NAV tip invested %; else book weights; else metrics.
 * Never mix live weights with book weights. Do not clamp >100 under an
 * accounting-tip label — surface the tip value.
 */
export function resolveInvestedPct(args: {
  tipInvestedPct: number | null | undefined;
  bookWeightInvestedPct: number | null | undefined;
  metricsInvestedPct: number | null | undefined;
}): { investedPct: number | null; definition: InvestedDefinition } {
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

type NavPoint = {
  date: string;
  nav: number;
  day_return_pct?: number | null;
  source?: string | null;
  series_seam?: boolean | null;
};

/** True when the tip row starts a new source run — no return may cross it. */
export function crossesNavSeam(tip: NavPoint, prior: NavPoint | null): boolean {
  if (!prior) return false;
  if (tip.series_seam === true) return true;
  const tipSource = tip.source ?? null;
  const priorSource = prior.source ?? null;
  return tipSource != null && priorSource != null && tipSource !== priorSource;
}

/** Seam-guarded tip day return: seam → null before any stored value can bypass. */
export function derivedDayReturnPct(tip: NavPoint, prior: NavPoint | null): number | null {
  if (crossesNavSeam(tip, prior)) return null;
  if (tip.day_return_pct != null && Number.isFinite(tip.day_return_pct)) {
    return tip.day_return_pct;
  }
  if (!prior || !(prior.nav > 0)) return null;
  const gap = calendarDaysBetween(prior.date, tip.date);
  if (gap == null || gap < 1 || gap > MAX_DAY_RETURN_GAP_DAYS) return null;
  return (tip.nav / prior.nav - 1) * 100;
}

/** True on a legacy↔finalized flip (explicit flag or detected source change). */
export function isNavSeriesSeam(
  row: { series_seam?: boolean | null; source?: string | null },
  prevSource?: string | null,
): boolean {
  if (row.series_seam === true) return true;
  if (prevSource == null) return false;
  const source = row.source ?? null;
  return source != null && prevSource != null && source !== prevSource;
}

/** Dates where the stitched NAV series flips source. */
export function findNavSeriesSeams(
  rows: ReadonlyArray<{ date: string; source?: string | null; series_seam?: boolean | null }>,
): string[] {
  const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  const seams: string[] = [];
  let prevSource: string | null | undefined;
  for (const row of sorted) {
    if (prevSource !== undefined && isNavSeriesSeam(row, prevSource)) seams.push(row.date);
    prevSource = row.source ?? null;
  }
  return seams;
}

/** Rows of the most recent source run. Empty in → empty out. */
export function currentNavRun<
  T extends { date: string; source?: string | null; series_seam?: boolean | null },
>(rows: ReadonlyArray<T>): T[] {
  if (rows.length === 0) return [];
  const sorted = [...rows].sort((a, b) => a.date.localeCompare(b.date));
  const seams = findNavSeriesSeams(sorted);
  if (seams.length === 0) return sorted;
  const current = sorted.filter((row) => row.date >= seams[seams.length - 1]);
  return current.length ? current : sorted;
}

/**
 * Continuity step for one row, in percent. Prefers the row's own day return;
 * a seam row with no day return carries flat; implausible steps carry flat.
 */
export function navContinuityStepPct(
  row: NavRowInput,
  previous: NavRowInput,
): number {
  const daily = row.day_return_pct;
  if (daily != null && Number.isFinite(daily)) {
    return Math.abs(daily) <= CONTINUITY_MAX_STEP_PCT ? daily : 0;
  }
  if (!isNavSeriesSeam(row, previous.source ?? null) && previous.nav > 0) {
    const level = (row.nav / previous.nav - 1) * 100;
    if (Number.isFinite(level) && Math.abs(level) <= CONTINUITY_MAX_STEP_PCT) return level;
  }
  return 0;
}

/** Base-100 continuity chain over a stitched NAV series. Empty in → empty out. */
export function chainNavContinuity(
  rows: ReadonlyArray<NavRowInput>,
): Array<{ date: string; nav: number }> {
  const sorted = [...rows]
    .filter((row) => Number.isFinite(row.nav) && row.nav > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
  if (sorted.length === 0) return [];
  const chained = [{ date: sorted[0].date, nav: 100 }];
  let index = 100;
  for (let position = 1; position < sorted.length; position += 1) {
    index *= 1 + navContinuityStepPct(sorted[position], sorted[position - 1]) / 100;
    chained.push({ date: sorted[position].date, nav: index });
  }
  return chained;
}

export interface ContinuityPoint {
  date: string;
  nav: number;
  returnPct: number;
}

/**
 * Plot-ready NAV series: chained runs onto one base-100 index, then
 * forward-fill calendar gaps of up to CONTINUITY_MAX_FILL_DAYS flat.
 */
export function buildContinuityNavSeries(
  rows: ReadonlyArray<NavRowInput>,
): ContinuityPoint[] {
  const chained = chainNavContinuity(rows);
  if (chained.length === 0) return [];
  const points: ContinuityPoint[] = [];
  for (let position = 0; position < chained.length; position += 1) {
    const point = chained[position];
    if (position > 0) {
      const previous = chained[position - 1];
      const gap = calendarDaysBetween(previous.date, point.date);
      if (gap != null && gap > 1 && gap - 1 <= CONTINUITY_MAX_FILL_DAYS) {
        for (
          let cursor = nextIsoDate(previous.date);
          cursor < point.date;
          cursor = nextIsoDate(cursor)
        ) {
          points.push({
            date: cursor,
            nav: roundPct(previous.nav),
            returnPct: roundPct(previous.nav - 100),
          });
        }
      }
    }
    points.push({
      date: point.date,
      nav: roundPct(point.nav),
      returnPct: roundPct(point.nav - 100),
    });
  }
  return points;
}

/** Total return over an index series. Null with fewer than 2 points. */
export function periodReturnPct(values: number[]): number | null {
  if (values.length < 2) return null;
  const first = values[0];
  const last = values.at(-1);
  if (last == null || first <= 0 || !Number.isFinite(first) || !Number.isFinite(last)) {
    return null;
  }
  return roundPct((last / first - 1) * 100);
}

/** Since-inception % from first/last NAV levels. */
export function sinceInceptionPctFromNav(firstNav: number, lastNav: number): number | null {
  if (!(firstNav > 0) || !Number.isFinite(lastNav)) return null;
  return (lastNav / firstNav - 1) * 100;
}

/** Provenance of one NAV row. Unlabeled rows are estimates — never finalized. */
export function navRowContractLabel(row: {
  source?: string | null;
  contract?: string | null;
}): 'finalized_accounting' | 'legacy_estimate' {
  if (row.contract === 'finalized_accounting' || row.source === 'finalized_accounting') {
    return 'finalized_accounting';
  }
  return 'legacy_estimate';
}

/** Badge for the displayed NAV tip (latest dated row). */
export function navSeriesContractLabel(
  rows: Array<{ date?: string | null; source?: string | null; contract?: string | null }>,
): NavContractBadge {
  if (!rows.length) return 'empty';
  const dated = rows.filter((r) => typeof r.date === 'string' && (r.date as string).length > 0);
  const tip = dated.length
    ? [...dated].sort((a, b) => String(a.date).localeCompare(String(b.date))).at(-1)
    : rows[rows.length - 1];
  return navRowContractLabel(tip!);
}

/** Operator-facing contract badge copy. */
export function navContractBadgeLabel(contract: NavContractBadge): string {
  if (contract === 'finalized_accounting') return 'finalized accounting';
  if (contract === 'legacy_estimate') return 'legacy estimate';
  return 'no nav series';
}

export interface PerformanceSsotMeta {
  navContract: NavContractBadge;
  navAsOf: string | null;
  tipDayReturnPct: number | null;
  tipInvestedPct: number | null;
  tipCashPct: number | null;
  /** Metrics stamp, never overwritten with the NAV tip. */
  metricsAsOf: string | null;
  /** Signed divergence navAsOf − metricsAsOf. + = metrics behind NAV. */
  metricsLagDays: number | null;
  metricsLagging: boolean;
  bookAsOf: string | null;
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

/** Headline KPIs from the persisted accounting NAV series (no live overlay). */
export function persistedHeadlinesFromNav(
  nav: ReadonlyArray<{
    date: string;
    nav: number;
    invested_pct?: number | null;
    day_return_pct?: number | null;
    source?: string | null;
    series_seam?: boolean | null;
  }>,
  opts: { bookWeightInvestedPct?: number | null; metricsInvestedPct?: number | null } = {},
): PersistedPerformanceHeadlines {
  const sorted = [...nav]
    .filter((row) => finiteNav(row.nav))
    .sort((a, b) => a.date.localeCompare(b.date));
  const chained = chainNavContinuity(sorted);
  const first = chained[0] ?? null;
  const chainTip = chained.at(-1) ?? null;
  const tip = sorted.at(-1) ?? null;
  const prior = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  const sinceInceptionPct =
    chained.length >= 2 && first && chainTip
      ? sinceInceptionPctFromNav(first.nav, chainTip.nav)
      : null;
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

export function buildPerformanceSsotMeta(args: {
  navRows: ReadonlyArray<
    Pick<
      NavRowInput,
      'date' | 'source' | 'contract' | 'invested_pct' | 'day_return_pct' | 'series_seam'
    > & {
      nav?: number;
      cash_pct?: number | null;
    }
  >;
  metricsAsOf: string | null | undefined;
  snapshotDate: string | null | undefined;
  positionDates: readonly string[];
  positionMetricsAsOf: readonly (string | null | undefined)[];
  bookWeightInvestedPct?: number | null;
  metricsInvestedPct?: number | null;
}): PerformanceSsotMeta {
  const sorted = [...args.navRows].sort((a, b) => a.date.localeCompare(b.date));
  const tip = sorted.at(-1) ?? null;
  const navAsOf = tip?.date ?? null;
  const metricsStamp = args.metricsAsOf?.slice(0, 10) || null;
  const lag = navAsOf && metricsStamp ? calendarDaysBetween(metricsStamp, navAsOf) : null;
  const invested = resolveInvestedPct({
    tipInvestedPct: tip?.invested_pct ?? null,
    bookWeightInvestedPct: args.bookWeightInvestedPct ?? null,
    metricsInvestedPct: args.metricsInvestedPct ?? null,
  });
  const prior = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  const tipDay =
    tip && finiteNav(tip.nav)
      ? derivedDayReturnPct(
          {
            date: tip.date,
            nav: tip.nav,
            day_return_pct: tip.day_return_pct,
            source: tip.source,
            series_seam: tip.series_seam,
          },
          prior && finiteNav(prior.nav)
            ? {
                date: prior.date,
                nav: prior.nav,
                day_return_pct: prior.day_return_pct,
                source: prior.source,
                series_seam: prior.series_seam,
              }
            : null,
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
    metricsAsOf: metricsStamp,
    metricsLagDays: lag,
    metricsLagging: lag != null && Math.abs(lag) >= METRICS_DIVERGENCE_TOLERANCE_DAYS,
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
  tolerancePp = PERSISTED_KPI_TOLERANCE_PP,
): boolean {
  if (briefSincePct == null || tearsheetNetReturnPct == null) return false;
  return Math.abs(briefSincePct - tearsheetNetReturnPct) <= tolerancePp;
}

/** Divergence chrome: + lag → metrics behind NAV; − lag → NAV tip behind metrics. */
export function metricsDivergenceBadgeLabel(
  meta: Pick<PerformanceSsotMeta, 'metricsLagging' | 'metricsLagDays'>,
): string | null {
  if (!meta.metricsLagging || meta.metricsLagDays == null) return null;
  if (meta.metricsLagDays > 0) return 'metrics lag';
  if (meta.metricsLagDays < 0) return 'nav lag';
  return null;
}

/** Signed lag direction for the contract `stale.lag_direction` field. */
export function lagDirection(lagDays: number | null): 'metrics lag' | 'nav lag' | null {
  if (lagDays == null || lagDays === 0) return null;
  return lagDays > 0 ? 'metrics lag' : 'nav lag';
}

/** Live overlay is active only when marks moved the index vs the book tip. */
export function isLiveMarksOverlay(liveVsMarkPct: number | null | undefined): boolean {
  return liveVsMarkPct != null && Math.abs(liveVsMarkPct) > 1e-9;
}

/** Prefer SPY, else first dashboard ticker with history. */
export function pickBriefBenchmarkTicker(
  benchmarks: Record<string, { history?: readonly unknown[] | null } | undefined>,
): string | null {
  if (benchmarks[DEFAULT_BRIEF_BENCHMARK_TICKER]?.history?.length) {
    return DEFAULT_BRIEF_BENCHMARK_TICKER;
  }
  for (const t of DASHBOARD_BENCHMARK_TICKERS) {
    if (benchmarks[t]?.history?.length) return t;
  }
  return null;
}

/** Sort universe: priority tickers first (if present), then A–Z. */
export function sortTickerUniverse(tickers: string[]): string[] {
  const upper = tickers.map((t) => String(t).toUpperCase().trim()).filter(Boolean);
  const set = new Set(upper);
  const priority = DASHBOARD_BENCHMARK_TICKERS.filter((t) => set.has(t as string));
  const priorityTickers = DASHBOARD_BENCHMARK_TICKERS as readonly string[];
  const rest = [...set].filter((t) => !priorityTickers.includes(t)).sort();
  return [...priority, ...rest];
}

// ─── Overlap-gated relative metrics ───

export interface BenchmarkPoint {
  date: string;
  price: number;
}

/**
 * Align NAV and benchmark to common dates (as-of forward fill on benchmark),
 * then emit overlapping daily simple returns for both series.
 */
export function overlappingDailyReturns(
  navHistory: ReadonlyArray<{ date: string; nav: number }>,
  benchmarkHistory: ReadonlyArray<BenchmarkPoint>,
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
    if (
      priorNav != null &&
      priorNav > 0 &&
      priorBench != null &&
      priorBench > 0 &&
      bPrice != null &&
      bPrice > 0
    ) {
      port.push(row.nav / priorNav - 1);
      benchRets.push(bPrice / priorBench - 1);
    }
    priorNav = row.nav;
    if (bPrice != null && bPrice > 0) priorBench = bPrice;
  }
  return { port, bench: benchRets };
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

/** OLS beta of portfolio daily returns on benchmark daily returns. */
export function olsBeta(
  portDaily: readonly number[],
  benchDaily: readonly number[],
): number | null {
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

/** Annualized information ratio from overlapping daily active returns. */
export function informationRatioFromDaily(
  portDaily: readonly number[],
  benchDaily: readonly number[],
): number | null {
  const n = Math.min(portDaily.length, benchDaily.length);
  if (n < MIN_OVERLAP_DAYS) return null;
  const active: number[] = [];
  for (let i = 0; i < n; i++) active.push(portDaily[i] - benchDaily[i]);
  const te = sampleStd(active);
  if (te < 1e-12) return null;
  return (mean(active) / te) * Math.sqrt(TRADING_DAYS);
}

/** Clip a benchmark series to [startDate, endDate] by first ≥ start / last ≤ end. */
export function pickBenchmarkPoints(
  history: ReadonlyArray<BenchmarkPoint>,
  startDate: string,
  endDate: string,
): { start: BenchmarkPoint; end: BenchmarkPoint } | null {
  const sorted = [...history].sort((a, b) => a.date.localeCompare(b.date));
  const start = sorted.find((p) => p.date >= startDate);
  const end = [...sorted].reverse().find((p) => p.date <= endDate);
  if (!start || !end || start.date > end.date) return null;
  if (start.price <= 0 || end.price <= 0) return null;
  return { start, end };
}

/**
 * Portfolio vs benchmark over the aligned return window (first portfolio point →
 * last portfolio point, clipped to available benchmark history). Defaults to
 * SPY when present. Mirrors the Brief `inceptionVsBenchmark` helper.
 */
export function inceptionVsBenchmark(
  snaps: ReadonlyArray<NavRowInput>,
  benchmarks: Record<string, ReadonlyArray<BenchmarkPoint> | undefined>,
): {
  ticker: string;
  portPct: number;
  benchPct: number;
  excessPct: number;
  startDate: string;
} | null {
  const ticker = pickBriefBenchmarkTicker(
    Object.fromEntries(
      Object.entries(benchmarks).map(([k, v]) => [k, { history: v }]),
    ),
  );
  if (!ticker || snaps.length < 2) return null;
  const hist = benchmarks[ticker];
  if (!hist?.length) return null;
  const run = chainNavContinuity([...snaps]);
  if (run.length < 2) return null;
  const sortedBench = [...hist].sort((a, b) => a.date.localeCompare(b.date));
  const first = run[0];
  const last = run[run.length - 1];
  const startBench = sortedBench.find((p) => p.date >= first.date);
  const endBench = [...sortedBench].reverse().find((p) => p.date <= last.date);
  if (!startBench || !endBench || startBench.date > endBench.date) return null;
  if (last.nav <= 0 || first.nav <= 0 || startBench.price <= 0 || endBench.price <= 0) {
    return null;
  }
  const portPct = (last.nav / first.nav - 1) * 100;
  const benchPct = (endBench.price / startBench.price - 1) * 100;
  const startDate = first.date > startBench.date ? first.date : startBench.date;
  return { ticker, portPct, benchPct, excessPct: portPct - benchPct, startDate };
}

// ─── Ledger day events (Brief session_events) ───

export interface BookEventInput {
  date: string;
  ticker: string;
  event: string;
  weight_pct?: number | null;
  prev_weight_pct?: number | null;
  weight_change_pct?: number | null;
}

/** Weight move in percentage points, or null when unknown. */
export function eventWeightDeltaPp(event: BookEventInput): number | null {
  if (event.weight_change_pct != null && Number.isFinite(event.weight_change_pct)) {
    return event.weight_change_pct;
  }
  if (event.weight_pct != null && event.prev_weight_pct != null) {
    return event.weight_pct - event.prev_weight_pct;
  }
  return null;
}

/**
 * Material book event. OPEN/EXIT without measurable weights still count;
 * HOLD never counts; sub-0.05pp churn does not count.
 */
export function isMaterialBookEvent(event: BookEventInput): boolean {
  const kind = (event.event || '').trim().toUpperCase();
  if (!kind || kind === 'HOLD') return false;
  const delta = eventWeightDeltaPp(event);
  if (delta == null) return kind === 'OPEN' || kind === 'EXIT';
  return Number(delta.toFixed(1)) !== 0;
}

/**
 * Material ledger rows for a single calendar date, largest |Δw| first.
 * Honest empty when that day has no decision-grade moves — never borrow an
 * older day.
 */
export function selectBriefLedgerDayEvents(
  events: ReadonlyArray<BookEventInput> | null | undefined,
  sessionDate: string | null | undefined,
): BookEventInput[] {
  const session = sessionDate?.trim() || null;
  if (!session) return [];
  const absDelta = (e: BookEventInput): number => Math.abs(eventWeightDeltaPp(e) ?? 0);
  return (events ?? [])
    .filter((e) => e.date === session && isMaterialBookEvent(e))
    .sort((a, b) => {
      const bySize = absDelta(b) - absDelta(a);
      if (bySize !== 0) return bySize;
      return a.ticker.localeCompare(b.ticker);
    });
}
