/**
 * GET /performance — Tearsheet bundle: one contracted NAV series,
 * benchmark-relative headline, overlap-gated alpha/IR (contract §6.4).
 *
 * Served by this shared `getPerformanceBundle` builder, not recomputed per
 * consumer. NAV chart is the single base-100 continuity index over the
 * accounting rows (each row's own day return; calendar gaps ≤ 4 days
 * forward-fill; tip badge from the latest dated row only). Excess = Rp − Rb
 * over the NAV-aligned benchmark window. Alpha (Jensen) and IR need ≥ 20
 * overlapping daily return pairs — null below the floor, never invented.
 * Lag is signed UTC calendar days and symmetric (`metrics lag` / `nav lag`).
 */

import {
  buildContinuityNavSeries,
  buildPerformanceSsotMeta,
  calendarDaysBetween,
  crossesNavSeam,
  currentNavRun,
  derivedDayReturnPct,
  informationRatioFromDaily,
  lagDirection,
  navSeriesContractLabel,
  olsBeta,
  overlappingDailyReturns,
  periodReturnPct,
  pickBenchmarkPoints,
  type BenchmarkPoint,
  type NavRowInput,
  type PerformanceSsotMeta,
} from './ssot';

export type PerformanceWindow = 'inception' | '1y' | '6m' | '3m';

const WINDOW_DAYS: Record<PerformanceWindow, number | null> = {
  inception: null,
  '1y': 365,
  '6m': 182,
  '3m': 91,
};

export interface PerformanceBook {
  navRows: NavRowInput[];
  /** Metrics stamp, never overwritten with the NAV tip. */
  metricsAsOf: string | null;
  benchmarkHistory: BenchmarkPoint[];
  /**
   * SSOT-chrome legs for the nested `ssot` object. Optional so stub/test
   * books keep working — absent legs degrade honestly (bookAsOf null,
   * marksUnstamped true) rather than failing the route.
   */
  snapshotDate?: string | null;
  positionDates?: string[];
  positionMetricsAsOf?: (string | null)[];
  bookWeightInvestedPct?: number | null;
  metricsInvestedPct?: number | null;
}

export interface PerformanceData {
  nav: {
    tip_date: string | null;
    base100_tip: number | null;
    points: { date: string; index: number; day_return_pct: number | null }[];
  };
  metrics: {
    day_return_pct: number | null;
    since_inception_pct: number | null;
    excess_return_pct: number | null;
    alpha_pct: number | null;
    information_ratio: number | null;
    beta: number | null;
    overlap_days: number;
  };
  benchmark: { ticker: string; aligned_start: string | null };
  stale: {
    lag_days: number | null;
    lag_direction: 'metrics lag' | 'nav lag' | null;
    metrics_as_of: string | null;
  };
  /**
   * Full SSOT chrome (camelCase `PerformanceSsotMeta` shape, identical to the
   * dashboard client's type). Served so dashboard surfaces can consume the
   * invested precedence + seam/marks chrome without re-deriving it.
   */
  ssot: PerformanceSsotMeta;
}

export interface PerformanceQuery {
  asOf: string | null;
  retrievalPin: string | null;
  benchmark: string;
  window: PerformanceWindow;
}

/** Validate the §6.4 query params. */
export function parsePerformanceQuery(
  search: URLSearchParams,
): { ok: true; query: PerformanceQuery } | { ok: false; code: string; message: string } {
  const asOf = search.get('asOf');
  if (asOf != null && !/^\d{4}-\d{2}-\d{2}$/.test(asOf)) {
    return { ok: false, code: 'bad_request', message: 'malformed asOf (want YYYY-MM-DD)' };
  }
  const retrievalPin = search.get('retrieval_pin');
  if (retrievalPin != null && retrievalPin.length > 128) {
    return { ok: false, code: 'bad_request', message: 'retrieval_pin longer than 128 chars' };
  }
  const benchmarkRaw = (search.get('benchmark') ?? 'SPY').trim().toUpperCase();
  if (!/^[A-Z0-9.=-]{1,12}$/.test(benchmarkRaw)) {
    return { ok: false, code: 'bad_request', message: 'malformed benchmark ticker' };
  }
  const windowRaw = search.get('window') ?? 'inception';
  if (windowRaw !== 'inception' && windowRaw !== '1y' && windowRaw !== '6m' && windowRaw !== '3m') {
    return { ok: false, code: 'bad_request', message: 'window must be inception|1y|6m|3m' };
  }
  return { ok: true, query: { asOf, retrievalPin, benchmark: benchmarkRaw, window: windowRaw } };
}

function addDays(date: string, days: number): string {
  const t = Date.parse(`${date}T00:00:00Z`) + days * 86_400_000;
  return new Date(t).toISOString().slice(0, 10);
}

/**
 * Build the §6.4 `data` object. The since-% comes from the same chained
 * series the chart plots, so headline and chart always agree.
 */
export function getPerformanceBundle(
  book: PerformanceBook,
  benchmarkTicker: string,
  window: PerformanceWindow = 'inception',
): PerformanceData {
  const sorted = [...book.navRows].sort((a, b) => a.date.localeCompare(b.date));
  const tip = sorted.at(-1) ?? null;
  const prior = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  const tipDate = tip?.date ?? null;

  const windowDays = WINDOW_DAYS[window];
  const windowed =
    windowDays != null && tipDate
      ? sorted.filter((r) => r.date >= addDays(tipDate, -windowDays))
      : sorted;

  const series = buildContinuityNavSeries(windowed);
  const sincePct = periodReturnPct(series.map((p) => p.nav));
  const base100Tip = series.at(-1)?.nav ?? null;

  const dayReturn = tip ? derivedDayReturnPct(tip, prior) : null;

  // Benchmark-relative headline over the NAV-aligned window. Rebased on the
  // current source run so the seam day never enters the estimator.
  const run = currentNavRun(sorted.filter((r) => Number.isFinite(r.nav) && r.nav > 0));
  const bench = [...book.benchmarkHistory].sort((a, b) => a.date.localeCompare(b.date));
  let excess: number | null = null;
  let alpha: number | null = null;
  let ir: number | null = null;
  let beta: number | null = null;
  let overlap = 0;
  let alignedStart: string | null = null;
  if (run.length >= 2 && bench.length >= 2 && tipDate) {
    const startDate = run[0].date;
    const clipped = pickBenchmarkPoints(bench, startDate, tipDate);
    if (clipped) {
      const portPct = (run[run.length - 1].nav / run[0].nav - 1) * 100;
      const benchPct = (clipped.end.price / clipped.start.price - 1) * 100;
      excess = portPct - benchPct;
      alignedStart = startDate > clipped.start.date ? startDate : clipped.start.date;
      const { port, bench: benchRets } = overlappingDailyReturns(
        run.map((r) => ({ date: r.date, nav: r.nav })),
        bench,
      );
      overlap = Math.min(port.length, benchRets.length);
      beta = olsBeta(port, benchRets);
      if (beta != null) alpha = portPct - beta * benchPct;
      ir = informationRatioFromDaily(port, benchRets);
    }
  }

  const metricsAsOf = book.metricsAsOf?.slice(0, 10) || null;
  const lag = tipDate && metricsAsOf ? calendarDaysBetween(metricsAsOf, tipDate) : null;

  // Per-point day return follows the plotted continuity step; the headline
  // tip return stays seam-guarded (null across seams, never a phantom jump).
  const points = series.map((p, i) => ({
    date: p.date,
    index: p.nav,
    day_return_pct:
      i === 0
        ? null
        : series[i - 1].nav > 0
          ? +(((p.nav / series[i - 1].nav - 1) * 100).toFixed(6))
          : null,
  }));

  const ssot = buildPerformanceSsotMeta({
    navRows: book.navRows,
    metricsAsOf: book.metricsAsOf,
    snapshotDate: book.snapshotDate ?? null,
    positionDates: book.positionDates ?? [],
    positionMetricsAsOf: book.positionMetricsAsOf ?? [],
    bookWeightInvestedPct: book.bookWeightInvestedPct ?? null,
    metricsInvestedPct: book.metricsInvestedPct ?? null,
  });

  return {
    nav: { tip_date: tipDate, base100_tip: base100Tip, points },
    ssot,
    metrics: {
      day_return_pct: dayReturn,
      since_inception_pct: sincePct,
      excess_return_pct: excess,
      alpha_pct: alpha,
      information_ratio: ir,
      beta,
      overlap_days: overlap,
    },
    benchmark: { ticker: benchmarkTicker, aligned_start: alignedStart },
    stale: { lag_days: lag, lag_direction: lagDirection(lag), metrics_as_of: metricsAsOf },
  };
}

export interface PerformanceProvenance {
  source: string;
  tip_date: string | null;
  contract: 'finalized_accounting' | 'legacy_estimate' | null;
  seam: boolean;
  marks: 'stored' | 'market_api' | 'unavailable';
}

/** Badge inputs for the §6.4 tip. Marks are NAV-level — always `stored` when stamped. */
export function buildPerformanceProvenance(book: PerformanceBook): PerformanceProvenance {
  const sorted = [...book.navRows].sort((a, b) => a.date.localeCompare(b.date));
  const tip = sorted.at(-1) ?? null;
  const prior = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  const contract = navSeriesContractLabel(sorted);
  return {
    source: 'public_accounting_nav_history',
    tip_date: tip?.date ?? null,
    contract: contract === 'empty' ? null : contract,
    seam: tip ? crossesNavSeam(tip, prior) : false,
    marks: tip ? 'stored' : 'unavailable',
  };
}

// ─── Mount (scaffold wiring) ───

export interface PerformanceDeps {
  /**
   * House-book + benchmark read for the request. Benchmark closes come from
   * the market API over the NAV window (paginated upstream); an empty answer
   * flows through as an empty series — never a Supabase fallback.
   */
  loadPerformanceBook: (
    asOf: string | null,
    benchmark: string,
    window: PerformanceWindow,
  ) => Promise<PerformanceBook | null>;
}

function errorBody(code: string, message: string, retrievalPin: string | null): object {
  return { error: { code, message, details: {}, retrieval_pin: retrievalPin } };
}

/** Register GET /performance on a minimal structural registrar. */
export function registerPerformanceRoutes(
  onGet: (path: string, handler: (req: Request) => Promise<Response>) => void,
  deps: PerformanceDeps,
): void {
  onGet('/performance', async (req: Request) => {
    const url = new URL(req.url);
    const parsed = parsePerformanceQuery(url.searchParams);
    const pin = parsed.ok ? parsed.query.retrievalPin : url.searchParams.get('retrieval_pin');
    if (!parsed.ok) {
      return Response.json(errorBody(parsed.code, parsed.message, pin), { status: 400 });
    }
    const book = await deps.loadPerformanceBook(
      parsed.query.asOf,
      parsed.query.benchmark,
      parsed.query.window,
    );
    if (!book) {
      return Response.json(errorBody('not_found', 'no committed book', pin), { status: 404 });
    }
    const data = getPerformanceBundle(book, parsed.query.benchmark, parsed.query.window);
    const provenance = buildPerformanceProvenance(book);
    return Response.json({ data, as_of: data.nav.tip_date, retrieval_pin: pin, provenance });
  });
}
