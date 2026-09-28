/**
 * GET /benchmarks — benchmark universe + aligned series for a NAV window
 * (contract §6.7).
 *
 * R2-API-only with benchmark-key fallback: the route layer fetches closes
 * from the market API (`GET /v1/market/closes`, paginated); an empty answer
 * falls back to the benchmark keys with empty series — never a Supabase
 * fallback. Each series aligns to the NAV dates (as-of forward fill); sparse
 * or paginated history still renders when the remaining overlap meets the
 * §6.4 floor. Recomputing on comparison change is a client re-request with a
 * different `tickers` value, not server state.
 */

import {
  DASHBOARD_BENCHMARK_TICKERS,
  MIN_OVERLAP_DAYS,
  sortTickerUniverse,
} from './ssot';

/** Market-API close point (contract §6.7 series shape). */
export interface BenchmarkClose {
  date: string;
  close: number;
}

export interface BenchmarksData {
  universe: string[];
  series: Record<string, BenchmarkClose[]>;
  aligned_start: string | null;
  overlap_days: number;
}

export interface BenchmarksQuery {
  retrievalPin: string | null;
  tickers: string[] | null;
  from: string | null;
  to: string | null;
}

/** Validate the §6.7 query params. */
export function parseBenchmarksQuery(
  search: URLSearchParams,
): { ok: true; query: BenchmarksQuery } | { ok: false; code: string; message: string } {
  if (search.get('asOf') != null) {
    return { ok: false, code: 'bad_request', message: 'asOf is not supported on /benchmarks' };
  }
  const retrievalPin = search.get('retrieval_pin');
  if (retrievalPin != null && retrievalPin.length > 128) {
    return { ok: false, code: 'bad_request', message: 'retrieval_pin longer than 128 chars' };
  }
  const tickersRaw = search.get('tickers');
  let tickers: string[] | null = null;
  if (tickersRaw != null && tickersRaw.trim() !== '') {
    tickers = [...new Set(
      tickersRaw
        .split(',')
        .map((t) => t.trim().toUpperCase())
        .filter((t) => /^[A-Z0-9.=-]{1,12}$/.test(t)),
    )];
    if (tickers.length === 0 || tickers.length > 20) {
      return { ok: false, code: 'bad_request', message: 'tickers must list 1-20 valid symbols' };
    }
  }
  const from = search.get('from');
  const to = search.get('to');
  for (const d of [from, to]) {
    if (d != null && !/^\d{4}-\d{2}-\d{2}$/.test(d)) {
      return { ok: false, code: 'bad_request', message: 'from/to must be YYYY-MM-DD' };
    }
  }
  if (from && to && from > to) {
    return { ok: false, code: 'bad_request', message: 'from must not be after to' };
  }
  return { ok: true, query: { retrievalPin, tickers, from, to } };
}

/**
 * Resolve the benchmark universe. Explicit `tickers` win; else the market-API
 * universe (`GET /v1/market/tickers`); else the dashboard key list (#4053).
 * R2-API-only — no Supabase fallback at any step.
 */
export function resolveBenchmarkUniverse(
  requested: string[] | null,
  marketTickers: string[] | null | undefined,
): string[] {
  if (requested && requested.length > 0) return sortTickerUniverse(requested);
  if (marketTickers && marketTickers.length > 0) return sortTickerUniverse(marketTickers);
  return [...DASHBOARD_BENCHMARK_TICKERS];
}

/**
 * Align one benchmark series to NAV dates (as-of forward fill): each NAV date
 * carries the latest close on or before it. Dates before the first close get
 * no point — the window visibly starts where history starts.
 */
export function alignBenchmarkSeries(
  navDates: ReadonlyArray<string>,
  closes: ReadonlyArray<BenchmarkClose>,
): BenchmarkClose[] {
  const sorted = [...closes]
    .filter((p) => Number.isFinite(p.close) && p.close > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
  if (sorted.length === 0) return [];
  const out: BenchmarkClose[] = [];
  let ci = -1;
  for (const date of [...navDates].sort()) {
    while (ci + 1 < sorted.length && sorted[ci + 1].date <= date) ci += 1;
    if (ci >= 0) out.push({ date, close: sorted[ci].close });
  }
  return out;
}

export interface BenchmarksBook {
  /** NAV dates in the window (ascending or not — sorted internally). */
  navDates: string[];
  /** Market-API closes keyed by ticker (empty when the API had nothing). */
  marketCloses: Record<string, BenchmarkClose[]>;
  /** Universe from `GET /v1/market/tickers` (null when unavailable). */
  marketUniverse: string[] | null;
}

/**
 * Build the §6.7 `data` object. Tickers with no market rows keep an empty
 * series under their key (fallback to keys, honest gap — never invented
 * closes). `overlap_days` counts NAV dates covered for every universe ticker.
 */
export function buildBenchmarksData(
  book: BenchmarksBook,
  tickers: string[] | null,
  from: string | null,
  to: string | null,
): BenchmarksData {
  const universe = resolveBenchmarkUniverse(tickers, book.marketUniverse);
  const navDates = [...new Set(book.navDates)].sort().filter((d) => {
    if (from && d < from) return false;
    if (to && d > to) return false;
    return true;
  });
  const series: Record<string, BenchmarkClose[]> = {};
  for (const t of universe) {
    series[t] = alignBenchmarkSeries(navDates, book.marketCloses[t] ?? []);
  }
  const covered = navDates.filter((d) =>
    universe.every((t) => series[t].some((p) => p.date === d)),
  );
  return {
    universe,
    series,
    aligned_start: covered.at(0) ?? null,
    overlap_days: covered.length,
  };
}

/** True when the remaining overlap still clears the alpha/IR floor. */
export function benchmarkOverlapMeetsFloor(overlapDays: number): boolean {
  return overlapDays >= MIN_OVERLAP_DAYS;
}

// ─── Mount (scaffold wiring) ───

export interface BenchmarksDeps {
  /**
   * NAV window + market-API reads. `marketCloses` holds paginated
   * `fetchComparablePriceHistory`-style closes; empty when the market API
   * had nothing — the bundle falls back to keys, never to Supabase.
   */
  loadBenchmarksBook: (from: string | null, to: string | null) => Promise<BenchmarksBook | null>;
}

function errorBody(code: string, message: string, retrievalPin: string | null): object {
  return { error: { code, message, details: {}, retrieval_pin: retrievalPin } };
}

/** Register GET /benchmarks on a minimal structural registrar. */
export function registerBenchmarksRoutes(
  onGet: (path: string, handler: (req: Request) => Promise<Response>) => void,
  deps: BenchmarksDeps,
): void {
  onGet('/benchmarks', async (req: Request) => {
    const url = new URL(req.url);
    const parsed = parseBenchmarksQuery(url.searchParams);
    const pin = parsed.ok ? parsed.query.retrievalPin : url.searchParams.get('retrieval_pin');
    if (!parsed.ok) {
      return Response.json(errorBody(parsed.code, parsed.message, pin), { status: 400 });
    }
    const book = await deps.loadBenchmarksBook(parsed.query.from, parsed.query.to);
    if (!book) {
      return Response.json(errorBody('not_found', 'no NAV window', pin), { status: 404 });
    }
    const data = buildBenchmarksData(
      book,
      parsed.query.tickers,
      parsed.query.from,
      parsed.query.to,
    );
    const tipDate = [...book.navDates].sort().at(-1) ?? null;
    return Response.json({
      data,
      as_of: tipDate,
      retrieval_pin: pin,
      provenance: {
        source: 'market_api',
        tip_date: tipDate,
        contract: null,
        seam: false,
        marks: 'market_api',
      },
    });
  });
}
