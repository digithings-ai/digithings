/**
 * Slice 0003 routes: `GET /portfolio` (full §6.1 body), `GET /allocations`
 * (§6.2, folded valuations), `GET /nav-series` (§6.6, seam-chained series).
 *
 * Mount contract for the merge step (Slice 2 owns `src/index.ts`,
 * `package.json`, `wrangler.toml` — do NOT import from `./index` here; pin
 * to the CONTRACT.md surface only):
 *
 *   import { mountEnvelopeRoutes } from "./envelope";
 *   mountEnvelopeRoutes((method, path, handler) => app.get(path, handler), source);
 *
 * `addRoute` is router-agnostic (works with the scaffold's raw-`Request`
 * switch or a Hono-style `.get`). `source` is the house-pinned upstream
 * read; the merge step implements it over Slice 2's `restClient`
 * (`daily_snapshots` + `positions` filtered to the house workspace, NAV via
 * `public_accounting_nav_history`, closes via `GET /v1/market/closes`,
 * R2-API-only). Small envelope/param helpers below mirror CONTRACT.md
 * §1/§2 so this file is self-contained; the merge step swaps them for
 * `errorResponse` / `buildProvenance` / `parseCommonParams` from `./index`.
 *
 * Pure builders live in `./portfolio`, `./allocations`, `./nav-series`,
 * `./invested`, `./book`, `./committed-book` (vitest parity targets).
 * No secrets here — the service-role key stays in worker secrets, used only
 * inside `source`. No time/tool-call budgets anywhere.
 */

import {
  buildAllocationsData,
  type AllocationPositionInput,
  type MarketCloseFill,
} from './allocations';
import {
  buildNavSeries,
  forwardFillCalendarGaps,
  isNavSeriesSeam,
  navRowContractLabel,
  type NavContract,
} from './nav-series';
import { buildPortfolioData, type PortfolioNavTipInput } from './portfolio';
import { resolveInvestedPct } from './invested';
import { committedBookDate as committedBookDatePure } from './committed-book';

export interface CommittedBookSnapshot {
  snapshotDate: string;
  bookAsOf: string;
  positionDates: readonly string[];
  /** Committed-date rows with valuation fields (`weightActual` = weight_pct). */
  positions: ReadonlyArray<AllocationPositionInput>;
  navRows: ReadonlyArray<PortfolioNavTipInput>;
  metricsInvestedPct: number | null;
  metricsAsOf: string | null;
}

/** House-pinned upstream read, implemented by the route layer at merge. */
export interface EnvelopeSource {
  /** Committed book for `asOf` (null = latest committed); null when none. */
  loadBook(
    asOf: string | null,
    retrievalPin: string | null,
  ): Promise<CommittedBookSnapshot | null>;
  /** R2-API-only closes; empty map when the market API is unset. */
  loadMarketCloses(
    tickers: readonly string[],
    retrievalPin: string | null,
  ): Promise<ReadonlyMap<string, MarketCloseFill>>;
}

export type RouteHandler = (req: Request) => Promise<Response>;
export type AddRoute = (method: 'GET', path: string, handler: RouteHandler) => void;

export function mountEnvelopeRoutes(addRoute: AddRoute, source: EnvelopeSource): void {
  addRoute('GET', '/portfolio', (req) => handleFullPortfolio(req, source));
  addRoute('GET', '/allocations', (req) => handleAllocations(req, source));
  addRoute('GET', '/nav-series', (req) => handleNavSeries(req, source));
}

// --- Self-contained CONTRACT.md §1/§2 surface (merge: swap for ./index) ---

type EnvelopeErrorCode = 'bad_request' | 'not_found' | 'upstream_empty' | 'internal';

const ERROR_STATUS: Record<EnvelopeErrorCode, number> = {
  bad_request: 400,
  not_found: 404,
  upstream_empty: 502,
  internal: 500,
};

function sliceError(
  code: EnvelopeErrorCode,
  message: string,
  retrievalPin: string | null,
  details: Record<string, unknown> = {},
): Response {
  return Response.json(
    { error: { code, message, details, retrieval_pin: retrievalPin } },
    { status: ERROR_STATUS[code] },
  );
}

interface SliceProvenance {
  source: string;
  tip_date: string | null;
  contract: NavContract | null;
  seam: boolean;
  marks: 'stored' | 'market_api' | 'unavailable';
}

function sliceOk(
  data: unknown,
  asOf: string | null,
  retrievalPin: string | null,
  provenance: SliceProvenance,
): Response {
  return Response.json({
    data,
    as_of: asOf,
    retrieval_pin: retrievalPin,
    provenance,
  });
}

const AS_OF_RE = /^\d{4}-\d{2}-\d{2}$/;

function validDate(v: string): boolean {
  if (!AS_OF_RE.test(v)) return false;
  const d = new Date(`${v}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === v;
}

function parseSliceParams(url: URL): { asOf: string | null; retrievalPin: string | null } {
  const retrievalPin = url.searchParams.get('retrieval_pin');
  if (retrievalPin !== null && retrievalPin.length > 128) {
    throw sliceError('bad_request', 'retrieval_pin exceeds 128 characters', null, {
      max_length: 128,
    });
  }
  const asOf = url.searchParams.get('asOf');
  if (asOf !== null && !validDate(asOf)) {
    throw sliceError('bad_request', 'asOf must be a calendar date YYYY-MM-DD', retrievalPin, {
      asOf,
    });
  }
  return { asOf, retrievalPin };
}

function parseOptionalDate(url: URL, name: string, retrievalPin: string | null): string | null {
  const v = url.searchParams.get(name);
  if (v !== null && !validDate(v)) {
    throw sliceError('bad_request', `${name} must be a calendar date YYYY-MM-DD`, retrievalPin, {
      [name]: v,
    });
  }
  return v;
}

// --- Handlers ---

async function withParams(
  req: Request,
  run: (params: { asOf: string | null; retrievalPin: string | null }) => Promise<Response>,
): Promise<Response> {
  let params: { asOf: string | null; retrievalPin: string | null };
  try {
    params = parseSliceParams(new URL(req.url));
  } catch (e) {
    return e as Response;
  }
  return run(params);
}

/** Full §6.1 body: raw-KPI invested + clamped envelope + reconciled rows. */
export async function handleFullPortfolio(
  req: Request,
  source: EnvelopeSource,
): Promise<Response> {
  return withParams(req, async ({ asOf, retrievalPin }) => {
    let book: CommittedBookSnapshot | null;
    try {
      book = await source.loadBook(asOf, retrievalPin);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return sliceError('upstream_empty', `book upstream read failed: ${message}`, retrievalPin);
    }
    if (!book) {
      return sliceError('not_found', 'no committed book for asOf', retrievalPin, { asOf });
    }
    // Defensive re-gate: never serve positions newer than the snapshot.
    const gated = committedBookDatePure(book.snapshotDate, book.positionDates);
    if (!gated) {
      return sliceError('not_found', 'no committed book for asOf', retrievalPin, {
        snapshot_date: book.snapshotDate,
      });
    }
    const result = buildPortfolioData({
      snapshotDate: book.snapshotDate,
      positionDates: book.positionDates,
      positions: book.positions,
      navRows: book.navRows,
      metricsInvestedPct: book.metricsInvestedPct,
      metricsAsOf: book.metricsAsOf,
    });
    if (!result.ok) {
      return sliceError('not_found', result.error.message, retrievalPin, { asOf });
    }
    const d = result.data;
    const tipDate = d.navTip?.date ?? null;
    const tipContract = d.navTip?.contract ?? null;
    return sliceOk(
      {
        book_as_of: d.bookAsOf,
        nav_tip: d.navTip
          ? {
              date: d.navTip.date,
              nav: d.navTip.nav,
              contract: d.navTip.contract,
              invested_pct: d.navTip.investedPct,
              cash_pct: d.navTip.cashPct,
              day_return_pct: d.navTip.dayReturnPct,
            }
          : null,
        seam: {
          crosses_nav_seam: d.seam.crossesNavSeam,
          lag_days: d.seam.lagDays,
          lag_direction: d.seam.lagDirection,
        },
        invested: {
          kpi_pct: d.invested.kpiPct,
          envelope_pct: d.invested.envelopePct,
          cash_pct: d.invested.cashPct,
          definition: d.invested.definition,
        },
        positions: d.positions.map((r) => ({
          ticker: r.ticker,
          weight_pct: r.weightPct,
          scaled_weight_pct: r.scaledWeightPct,
          is_cash: false,
        })),
      },
      d.bookAsOf,
      retrievalPin,
      {
        source: 'public_accounting_nav_history+daily_snapshots+positions',
        tip_date: tipDate,
        contract: tipContract,
        seam: d.seam.crossesNavSeam,
        marks: 'unavailable',
      },
    );
  });
}

/** §6.2 rows scaled into the §6.1 envelope with folded per-row valuations. */
export async function handleAllocations(
  req: Request,
  source: EnvelopeSource,
): Promise<Response> {
  return withParams(req, async ({ asOf, retrievalPin }) => {
    const url = new URL(req.url);
    const includeMarks = url.searchParams.get('include_marks');
    const wantMarks = includeMarks === null || includeMarks.toLowerCase() !== 'false';
    let book: CommittedBookSnapshot | null;
    try {
      book = await source.loadBook(asOf, retrievalPin);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return sliceError('upstream_empty', `book upstream read failed: ${message}`, retrievalPin);
    }
    if (!book) {
      return sliceError('not_found', 'no committed book for asOf', retrievalPin, { asOf });
    }
    const heldSum = book.positions
      .filter((p) => p.ticker.trim().toUpperCase() !== 'CASH')
      .reduce((s, p) => s + (p.weightActual ?? 0), 0);
    const tipInvested =
      [...book.navRows].sort((a, b) => a.date.localeCompare(b.date)).at(-1)?.investedPct ??
      null;
    const resolved = resolveInvestedPct({
      tipInvestedPct: tipInvested,
      bookWeightInvestedPct: heldSum,
      metricsInvestedPct: book.metricsInvestedPct,
    });
    let closes: ReadonlyMap<string, MarketCloseFill> = new Map();
    if (wantMarks) {
      const needy = book.positions
        .filter(
          (p) =>
            p.ticker.trim().toUpperCase() !== 'CASH' &&
            (p.metricsAsOf == null || String(p.metricsAsOf).trim() === '') &&
            p.entryPrice != null,
        )
        .map((p) => p.ticker);
      if (needy.length > 0) {
        try {
          closes = await source.loadMarketCloses(needy, retrievalPin);
        } catch {
          closes = new Map();
        }
      }
    }
    const data = buildAllocationsData({
      positions: book.positions,
      resolvedInvestedPct: resolved.investedPct,
      marketCloses: closes,
    });
    const provenanceMarks =
      data.rows.length === 0 || data.rows.every((r) => r.marks === 'unavailable')
        ? 'unavailable'
        : data.rows.some((r) => r.marks === 'market_api')
          ? 'market_api'
          : 'stored';
    return sliceOk(
      {
        book_as_of: book.bookAsOf,
        invested_pct: data.investedPct,
        cash_pct: data.cashPct,
        invested_definition: resolved.definition,
        rows: data.rows.map((r) => ({
          ticker: r.ticker,
          weight_pct: r.weightPct,
          scaled_weight_pct: r.scaledWeightPct,
          entry_price: r.entryPrice,
          current_price: r.currentPrice,
          unrealized_pct: r.unrealizedPct,
          marks: r.marks,
          marks_as_of: r.marksAsOf,
        })),
        marks_unstamped: data.marksUnstamped,
      },
      book.bookAsOf,
      retrievalPin,
      {
        source: 'public_accounting_nav_history+daily_snapshots+positions',
        tip_date:
          [...book.navRows].sort((a, b) => a.date.localeCompare(b.date)).at(-1)?.date ??
          null,
        contract:
          book.navRows.length > 0
            ? navRowContractLabel(
                [...book.navRows].sort((a, b) => a.date.localeCompare(b.date)).at(-1)!,
              )
            : null,
        seam: false,
        marks: wantMarks ? provenanceMarks : 'unavailable',
      },
    );
  });
}

/** §6.6 shared NAV + close series with per-point contract labels. */
export async function handleNavSeries(
  req: Request,
  source: EnvelopeSource,
): Promise<Response> {
  return withParams(req, async ({ asOf, retrievalPin }) => {
    const url = new URL(req.url);
    let from: string | null = null;
    let to: string | null = null;
    try {
      from = parseOptionalDate(url, 'from', retrievalPin);
      to = parseOptionalDate(url, 'to', retrievalPin);
    } catch (e) {
      return e as Response;
    }
    let book: CommittedBookSnapshot | null;
    try {
      book = await source.loadBook(asOf, retrievalPin);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return sliceError('upstream_empty', `book upstream read failed: ${message}`, retrievalPin);
    }
    if (!book) {
      return sliceError('not_found', 'no committed book for asOf', retrievalPin, { asOf });
    }
    const filtered = book.navRows.filter(
      (r) => (from === null || r.date >= from) && (to === null || r.date <= to),
    );
    const points = forwardFillCalendarGaps(buildNavSeries(filtered));
    const sorted = [...filtered].sort((a, b) => a.date.localeCompare(b.date));
    const tip = sorted.at(-1) ?? null;
    const hasSeam = sorted.some((r, i) =>
      i === 0 ? false : isNavSeriesSeam(r, sorted[i - 1].source ?? null),
    );
    return sliceOk(
      {
        tip: tip ? { date: tip.date, contract: navRowContractLabel(tip) } : null,
        points: points.map((p) => ({
          date: p.date,
          nav: p.nav,
          day_return_pct: p.dayReturnPct,
          contract: p.contract,
          index: p.index,
        })),
      },
      tip?.date ?? null,
      retrievalPin,
      {
        source: 'public_accounting_nav_history',
        tip_date: tip?.date ?? null,
        contract: tip ? navRowContractLabel(tip) : null,
        seam: hasSeam,
        marks: 'unavailable',
      },
    );
  });
}
