/**
 * GET /brief — Brief scoreboard KPIs with the persisted-vs-overlay decision
 * made in one place (contract §6.3).
 *
 * Persisted path first (same tip + ssot helpers as the Tearsheet); the live
 * overlay engages only when |liveVsMarkPct| > 0, and then the tile is labeled
 * `live marks` — never finalized accounting. The seam guard nulls persisted
 * day return when the tip crosses a NAV source seam. Overlay-off output matches
 * the Tearsheet headline within 0.05pp by construction (same persisted path).
 *
 * Pure + dependency-free. The route layer supplies the book snapshot; the
 * mount function wraps this file's builders in a Web-standard handler so the
 * scaffold router can register it without new dependencies.
 */

import {
  buildPerformanceSsotMeta,
  committedBookDate,
  crossesNavSeam,
  isLiveMarksOverlay,
  navContractBadgeLabel,
  navSeriesContractLabel,
  persistedHeadlinesFromNav,
  selectBriefLedgerDayEvents,
  type BookEventInput,
  type NavRowInput,
} from './ssot';

export type OverlayMode = 'auto' | 'off';

export interface BriefLiveInput {
  liveVsMarkPct: number;
  sinceInceptionPct: number | null;
  sinceInceptionStartDate: string | null;
  dayReturnPct: number | null;
  priceAsOfDate: string | null;
  excessReturnPct: number | null;
  benchmarkTicker: string | null;
}

export interface BriefBook {
  /** Accounting NAV rows (ascending or not — sorted internally). */
  navRows: NavRowInput[];
  /** Latest snapshot date (`daily_snapshots.date` tip). */
  snapshotDate: string | null;
  /** Position dates for the committed-book gate. */
  positionDates: string[];
  /** Per open-book row `metrics_as_of` (null = unstamped). */
  positionMetricsAsOf: (string | null | undefined)[];
  bookWeightInvestedPct: number | null;
  metricsInvestedPct: number | null;
  /** Metrics stamp (`portfolio_metrics.as_of_date`/`date`), never the NAV tip. */
  metricsAsOf: string | null;
  /** Live overlay KPIs (null = no live lane — persisted only). */
  live: BriefLiveInput | null;
  /** Ledger `position_events` slice for `session_events`. */
  ledgerEvents: BookEventInput[];
}

export interface BriefData {
  book_as_of: string | null;
  nav_tip: { date: string | null; nav: number | null; contract: string };
  day_return_pct: number | null;
  since_inception_pct: number | null;
  overlay: { active: boolean; live_vs_mark_pct: number; badge: string };
  invested_pct: number | null;
  session_events: BookEventInput[];
}

export interface BriefQuery {
  asOf: string | null;
  retrievalPin: string | null;
  overlay: OverlayMode;
}

/** Validate the §6.3 query params. Returns an error code/message on failure. */
export function parseBriefQuery(
  search: URLSearchParams,
): { ok: true; query: BriefQuery } | { ok: false; code: string; message: string } {
  const asOf = search.get('asOf');
  if (asOf != null && !/^\d{4}-\d{2}-\d{2}$/.test(asOf)) {
    return { ok: false, code: 'bad_request', message: 'malformed asOf (want YYYY-MM-DD)' };
  }
  const retrievalPin = search.get('retrieval_pin');
  if (retrievalPin != null && retrievalPin.length > 128) {
    return { ok: false, code: 'bad_request', message: 'retrieval_pin longer than 128 chars' };
  }
  const overlayRaw = search.get('overlay') ?? 'auto';
  if (overlayRaw !== 'auto' && overlayRaw !== 'off') {
    return { ok: false, code: 'bad_request', message: 'overlay must be "auto" or "off"' };
  }
  return { ok: true, query: { asOf, retrievalPin, overlay: overlayRaw } };
}

/**
 * Build the §6.3 `data` object. Overlay-off output is the persisted path
 * untouched, so it matches the Tearsheet headline within 0.05pp.
 */
export function buildBriefData(book: BriefBook, overlay: OverlayMode): BriefData {
  const persisted = persistedHeadlinesFromNav(book.navRows, {
    bookWeightInvestedPct: book.bookWeightInvestedPct,
    metricsInvestedPct: book.metricsInvestedPct,
  });
  const meta = buildPerformanceSsotMeta({
    navRows: book.navRows,
    metricsAsOf: book.metricsAsOf,
    snapshotDate: book.snapshotDate,
    positionDates: book.positionDates,
    positionMetricsAsOf: book.positionMetricsAsOf,
    bookWeightInvestedPct: book.bookWeightInvestedPct,
    metricsInvestedPct: book.metricsInvestedPct,
  });
  const bookAsOf =
    committedBookDate(book.snapshotDate, book.positionDates) ??
    meta.bookAsOf ??
    persisted.navAsOf;
  const liveOverlay =
    overlay === 'auto' && book.live != null && isLiveMarksOverlay(book.live.liveVsMarkPct);

  const live = book.live;

  const sincePct = liveOverlay
    ? (live?.sinceInceptionPct ?? persisted.sinceInceptionPct)
    : persisted.sinceInceptionPct;
  const dailyRet = liveOverlay
    ? (live?.dayReturnPct ?? persisted.dayReturnPct)
    : persisted.dayReturnPct;

  const tipNav = [...book.navRows].sort((a, b) => a.date.localeCompare(b.date)).at(-1) ?? null;
  return {
    book_as_of: bookAsOf,
    nav_tip: {
      date: persisted.navAsOf,
      nav: tipNav?.nav ?? null,
      contract: meta.navContract === 'empty' ? 'empty' : meta.navContract,
    },
    day_return_pct: dailyRet,
    since_inception_pct: sincePct,
    overlay: {
      active: liveOverlay,
      live_vs_mark_pct: live?.liveVsMarkPct ?? 0,
      badge: liveOverlay ? 'live marks' : navContractBadgeLabel(meta.navContract),
    },
    invested_pct: persisted.investedPct,
    session_events: selectBriefLedgerDayEvents(book.ledgerEvents, bookAsOf),
  };
}

export interface BriefProvenance {
  source: string;
  tip_date: string | null;
  contract: 'finalized_accounting' | 'legacy_estimate' | null;
  seam: boolean;
  marks: 'stored' | 'market_api' | 'unavailable';
}

/** Honest badge inputs for the §6.3 tip — derived from the book, never defaulted. */
export function buildBriefProvenance(book: BriefBook): BriefProvenance {
  const sorted = [...book.navRows].sort((a, b) => a.date.localeCompare(b.date));
  const tip = sorted.at(-1) ?? null;
  const prior = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  const contract = navSeriesContractLabel(sorted);
  return {
    source: 'public_accounting_nav_history',
    tip_date: tip?.date ?? null,
    contract: contract === 'empty' ? null : contract,
    seam: tip ? crossesNavSeam(tip, prior) : false,
    marks:
      book.positionMetricsAsOf.length === 0 ||
      book.positionMetricsAsOf.some((v) => v == null || String(v).trim() === '')
        ? 'unavailable'
        : 'stored',
  };
}

// ─── Mount (scaffold wiring) ──────────────────────────────────────────────────

export interface BriefDeps {
  /** House-book read for the requested `asOf` (null = latest committed). */
  loadBriefBook: (asOf: string | null) => Promise<BriefBook | null>;
}

function errorBody(code: string, message: string, retrievalPin: string | null): object {
  return { error: { code, message, details: {}, retrieval_pin: retrievalPin } };
}

/**
 * Register GET /brief on a minimal registrar. The registrar shape is
 * structural so the scaffold router can pass its own `get` through.
 */
export function registerBriefRoutes(
  onGet: (path: string, handler: (req: Request) => Promise<Response>) => void,
  deps: BriefDeps,
): void {
  onGet('/brief', async (req: Request) => {
    const url = new URL(req.url);
    const parsed = parseBriefQuery(url.searchParams);
    const pin = parsed.ok ? parsed.query.retrievalPin : url.searchParams.get('retrieval_pin');
    if (!parsed.ok) {
      return Response.json(errorBody(parsed.code, parsed.message, pin), { status: 400 });
    }
    const book = await deps.loadBriefBook(parsed.query.asOf);
    if (!book) {
      return Response.json(errorBody('not_found', 'no committed book', pin), { status: 404 });
    }
    const data = buildBriefData(book, parsed.query.overlay);
    const provenance = buildBriefProvenance(book);
    return Response.json({ data, as_of: data.book_as_of, retrieval_pin: pin, provenance });
  });
}
