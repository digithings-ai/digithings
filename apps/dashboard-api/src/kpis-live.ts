/**
 * GET /kpis/live — point-in-time live snapshot (contract §6.5).
 *
 * Snapshot only, not a stream: computed from the latest quotes the server can
 * see. Clients must not poll it as a realtime substitute — live marks arrive
 * via the client Realtime lane and render as a badged overlay. Numbers here
 * are `live marks` by definition and must never be labeled finalized
 * accounting.
 *
 * Math mirrors `computeLivePerformanceKpis` (packages/ui): live quote vs
 * `entry_price` drift is out of scope here — the snapshot drifts the book tip
 * by the weighted live-vs-mark move. Excess/alpha/IR need ≥ 20 overlapping
 * NAV/benchmark pairs. `overlay_eligible` is false when `liveVsMarkPct === 0`
 * or the book's `current_price` marks are all NULL.
 */

import {
  isLiveMarksOverlay,
  pickBenchmarkPoints,
  sinceInceptionPctFromNav,
  type BenchmarkPoint,
} from './ssot';

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

export interface LiveBook {
  positions: LiveKpiPosition[];
  navHistory: { date: string; nav: number }[];
  benchmarkHistory: BenchmarkPoint[];
  benchmarkTicker: string | null;
}

export interface LiveData {
  quote_date: string | null;
  live_vs_mark_pct: number;
  day_return_live_pct: number | null;
  since_inception_live_pct: number | null;
  excess_live_pct: number | null;
  overlay_eligible: boolean;
  universe: string[];
}

/** Weighted live move vs published marks. */
export function computeLiveVsMarkPct(positions: ReadonlyArray<LiveKpiPosition>): number {
  let move = 0;
  for (const p of positions) {
    const mark = p.markPrice;
    const price = p.effectivePrice;
    if (mark == null || mark <= 0 || price == null || price <= 0) continue;
    if (p.isLive) move += (p.weightPct / 100) * (price / mark - 1);
  }
  return move * 100;
}

/** Dominant price-as-of date across the book for KPI footnotes. */
export function derivePriceAsOfDate(
  positions: ReadonlyArray<LiveKpiPosition>,
): string | null {
  const asDate = (iso: string | null | undefined): string | null => {
    if (!iso) return null;
    const d = iso.slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : null;
  };
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

/**
 * NAV series for the overlapping estimator when a live tip may sit on a later
 * calendar day than the last accounting row. Keeps every accounting
 * observation and appends the live tip — dropping the last accounting row can
 * drop a valid overlap pair below the floor.
 */
export function navHistoryForLiveOverlap(
  sortedNav: ReadonlyArray<{ date: string; nav: number }>,
  endDate: string,
  liveNav: number,
): { date: string; nav: number }[] {
  const last = sortedNav.at(-1);
  if (!last) return [{ date: endDate, nav: liveNav }];
  if (endDate === last.date) return [...sortedNav.slice(0, -1), { date: endDate, nav: liveNav }];
  if (endDate > last.date) return [...sortedNav, { date: endDate, nav: liveNav }];
  return [...sortedNav];
}

/**
 * Day-return anchor: when marks sit after the latest accounting row, the
 * baseline is that latest close; when marks share the book date (post-EOD),
 * the baseline is the prior row so the printed return still reflects the last
 * completed session.
 */
export function dayReturnAnchorNav(
  sortedNav: ReadonlyArray<{ date: string; nav: number }>,
  priceAsOfDate: string | null,
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

/** Validate the §6.5 query params (no `asOf` — always latest quotes). */
export function parseLiveQuery(
  search: URLSearchParams,
): { ok: true; retrievalPin: string | null } | { ok: false; code: string; message: string } {
  if (search.get('asOf') != null) {
    return { ok: false, code: 'bad_request', message: 'asOf is not supported on /kpis/live' };
  }
  const retrievalPin = search.get('retrieval_pin');
  if (retrievalPin != null && retrievalPin.length > 128) {
    return { ok: false, code: 'bad_request', message: 'retrieval_pin longer than 128 chars' };
  }
  return { ok: true, retrievalPin };
}

/** Build the §6.5 `data` object from the latest quotes the server can see. */
export function buildLiveData(book: LiveBook): LiveData {
  const sortedNav = [...book.navHistory].sort((a, b) => a.date.localeCompare(b.date));
  const latestNavRow = sortedNav.length > 0 ? sortedNav[sortedNav.length - 1] : null;
  const latestNav = latestNavRow?.nav ?? null;
  const liveVsMarkPct = computeLiveVsMarkPct(book.positions);
  const liveNav = latestNav == null ? null : latestNav * (1 + liveVsMarkPct / 100);
  const priceAsOfDate = derivePriceAsOfDate(book.positions);
  const bookNavDate = latestNavRow?.date ?? null;

  const anchor = dayReturnAnchorNav(sortedNav, priceAsOfDate);
  const dayReturnPct =
    liveNav != null && anchor != null && anchor > 0 ? (liveNav / anchor - 1) * 100 : null;

  const firstNavRow = sortedNav.length > 0 ? sortedNav[0] : null;
  const sinceInceptionPct =
    liveNav != null && firstNavRow != null
      ? sinceInceptionPctFromNav(firstNavRow.nav, liveNav)
      : null;

  let excess: number | null = null;
  const benchTicker = book.benchmarkTicker;
  if (
    liveNav != null &&
    firstNavRow != null &&
    firstNavRow.nav > 0 &&
    book.benchmarkHistory?.length &&
    benchTicker
  ) {
    const endDate =
      priceAsOfDate && bookNavDate && priceAsOfDate > bookNavDate
        ? priceAsOfDate
        : (bookNavDate ?? priceAsOfDate ?? latestNavRow?.date ?? null);
    const startDate = firstNavRow.date;
    if (endDate) {
      const aligned = pickBenchmarkPoints(book.benchmarkHistory, startDate, endDate);
      if (aligned) {
        const portfolioReturnPct = (liveNav / firstNavRow.nav - 1) * 100;
        const benchmarkReturnPct = (aligned.end.price / aligned.start.price - 1) * 100;
        excess = portfolioReturnPct - benchmarkReturnPct;
      }
    }
  }

  const hasMarks = book.positions.some(
    (p) => p.markPrice != null && Number.isFinite(p.markPrice) && (p.markPrice as number) > 0,
  );
  const universe = [...new Set(book.positions.map((p) => p.ticker.trim().toUpperCase()))]
    .filter(Boolean)
    .sort();

  return {
    quote_date: priceAsOfDate,
    live_vs_mark_pct: liveVsMarkPct,
    day_return_live_pct: dayReturnPct,
    since_inception_live_pct: sinceInceptionPct,
    excess_live_pct: excess,
    overlay_eligible: isLiveMarksOverlay(liveVsMarkPct) && hasMarks,
    universe,
  };
}

// ─── Mount (scaffold wiring) ──────────────────────────────────────────────────

export interface LiveDeps {
  /** Latest quotes the server can see (market API snapshot, never a stream). */
  loadLiveBook: () => Promise<LiveBook | null>;
}

function errorBody(code: string, message: string, retrievalPin: string | null): object {
  return { error: { code, message, details: {}, retrieval_pin: retrievalPin } };
}

/** Register GET /kpis/live on a minimal structural registrar. */
export function registerLiveRoutes(
  onGet: (path: string, handler: (req: Request) => Promise<Response>) => void,
  deps: LiveDeps,
): void {
  onGet('/kpis/live', async (req: Request) => {
    const url = new URL(req.url);
    const parsed = parseLiveQuery(url.searchParams);
    if (!parsed.ok) {
      const pin = url.searchParams.get('retrieval_pin');
      return Response.json(errorBody(parsed.code, parsed.message, pin), { status: 400 });
    }
    const book = await deps.loadLiveBook();
    if (!book) {
      return Response.json(errorBody('not_found', 'no live quotes', parsed.retrievalPin), {
        status: 404,
      });
    }
    const data = buildLiveData(book);
    return Response.json({
      data,
      as_of: data.quote_date,
      retrieval_pin: parsed.retrievalPin,
      provenance: {
        source: 'market_api',
        tip_date: data.quote_date,
        contract: null,
        seam: false,
        marks: 'market_api',
      },
    });
  });
}
