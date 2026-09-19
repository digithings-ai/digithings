/**
 * Observability dashboard data access (Pillar 3D).
 *
 * Reads the decision track record (`decision_log`) the Decision Scorecard needs, plus
 * — via `fetchResearchRunDiagnostics` — run health from the anon-readable
 * `atlas_run_health` view (migration 041). Kept separate from `getFullDashboardData`
 * so the main Morning Read bundle stays lean; these fire only when their consumer mounts.
 *
 * Attribution and recommendation quality now live on Portfolio Attribution; per-position
 * risk remains on Holdings. Pipeline + Brief read run telemetry from `atlas_run_health` —
 * the curated projection that bypasses the base-table RLS on `atlas_run_diagnostics`
 * (migration 033). Spend telemetry (cost, tokens, error_summary, breakdown) is intentionally
 * excluded from the view; economics tiles render "—" on the public anon-key dashboard.
 *
 * Most queries are FAIL-SOFT: a missing/forbidden source (e.g. an empty book) resolves to an
 * empty result rather than throwing, so consumers render a clean empty state instead of an
 * error wall.
 *
 * Exception — accounting NAV (#2599 / #3029): `fetchPerformanceTearsheet` /
 * `getPerformanceBundle` FAIL CLOSED when `public_accounting_nav_history` errors.
 * Swallowing that into an empty series looked like a healthy empty book and hid
 * unapplied migrations 072–074.
 *
 * Performance SSOT (#3580): Brief persisted KPIs and Tearsheet share
 * `getPerformanceBundle()` / `buildPerformanceTearsheet` — one NAV adapter, one
 * contract badge. Live marks on Brief are a badged overlay only.
 */

import { supabase, isSupabaseConfigured } from './supabase';
import type { TableRow, ViewRow } from './database.types';
import type { ResearchRunDiagnostics, BenchmarkHistoryMap } from './types';
import type {
  BenchmarkComparison,
  PerformanceContributionSource,
  PerformanceTearsheet,
  PerformanceHoldingRow,
  PortfolioReturnPoint,
} from '@/components/tearsheet/types';
import type { ContributionReturnPoint } from '@digithings/ui';
import { DASHBOARD_BENCHMARK_TICKERS } from './benchmark-tickers';
import {
  ACCOUNTING_NAV_VIEW,
  PUBLIC_REALIZED_ATTRIBUTION_VIEW,
  AccountingNavContractError,
  accountingNavToHistoryShape,
  chainNavContinuity,
  type AccountingNavRow,
  type NavContinuityRow,
} from './accounting-views';
import {
  averageEntryAsOf,
  realizedReturnVsAverageEntry,
  roundPct,
  soldWeightPct,
} from './position-event-economics';
import { houseBook } from './house-workspace';
import { fetchMarketCloses } from './market-data';
import { isCashTicker } from './book-reconciliation';
import { committedBookDate } from './dashboard-ssot';
import {
  buildPerformanceSsotMeta,
  type PerformanceSsotMeta,
} from './performance-ssot';
import { fetchComparablePriceHistory } from './queries';

const DECISION_PAGE_SIZE = 1000;
const DECISION_MAX_ROWS = 50000;
const PERFORMANCE_HISTORY_LIMIT = 5000;
const ATTRIBUTION_LIMIT = 5000;
const ATTRIBUTION_PAGE_SIZE = 1000;
const ATTRIBUTION_MAX_ROWS = 50000;

export interface ObservabilityData {
  decisions: TableRow<'decision_log'>[];
}

export interface PortfolioAttributionData {
  attribution: TableRow<'position_attribution'>[];
  attributionDate: string | null;
  decisions: TableRow<'decision_log'>[];
}

/** Run a single-table read, logging + swallowing any error into an empty array. */
async function safeSelect<T>(
  label: string,
  run: (sb: NonNullable<typeof supabase>) => PromiseLike<{ data: T[] | null; error: unknown }>
): Promise<{ rows: T[]; ok: boolean }> {
  if (!supabase) return { rows: [], ok: false };
  try {
    const { data, error } = await run(supabase);
    if (error) {
      console.error(`Supabase ${label} query:`, error);
      return { rows: [], ok: false };
    }
    return { rows: data ?? [], ok: true };
  } catch (err) {
    console.error(`Supabase ${label} query threw:`, err);
    return { rows: [], ok: false };
  }
}

async function fetchDecisionHistory(): Promise<TableRow<'decision_log'>[]> {
  const decisions: TableRow<'decision_log'>[] = [];
  for (let offset = 0; offset < DECISION_MAX_ROWS; offset += DECISION_PAGE_SIZE) {
    const page = await safeSelect<TableRow<'decision_log'>>('decision_log', (sb) =>
      sb
        .from('decision_log')
        .select(
          'id,run_id,run_date,ticker,stance,conviction,thesis,benchmark,holding_days,status,actual_return,alpha,reflection,resolved_at,created_at'
        )
        .order('run_date', { ascending: false })
        .range(offset, offset + DECISION_PAGE_SIZE - 1)
    );
    decisions.push(...page.rows);
    if (!page.ok || page.rows.length < DECISION_PAGE_SIZE) break;
  }
  return decisions;
}

/**
 * Collect a paged read into one array (#3983).
 *
 * `fetchPage` receives inclusive PostgREST `.range()` offsets. Stops at the
 * first error or short page. `truncated` is true when `maxRows` was exhausted
 * on full pages, so callers can flag understated data instead of rendering it
 * silently.
 */
export async function collectPagedRows<T>(
  pageSize: number,
  maxRows: number,
  fetchPage: (from: number, to: number) => Promise<{ rows: T[]; ok: boolean }>
): Promise<{ rows: T[]; ok: boolean; truncated: boolean }> {
  const rows: T[] = [];
  for (let offset = 0; offset < maxRows; offset += pageSize) {
    const page = await fetchPage(offset, offset + pageSize - 1);
    rows.push(...page.rows);
    if (!page.ok) return { rows, ok: false, truncated: false };
    if (page.rows.length < pageSize) return { rows, ok: true, truncated: false };
  }
  return { rows, ok: true, truncated: true };
}

/**
 * Page the realized view from the plotted-window start (#3956 / #3983).
 * Orders by date then ticker so page boundaries are deterministic.
 */
function fetchRealizedAttribution(fromDate: string) {
  return collectPagedRows<ViewRow<'public_daily_realized_attribution'>>(
    ATTRIBUTION_PAGE_SIZE,
    ATTRIBUTION_MAX_ROWS,
    (from, to) =>
      safeSelect<ViewRow<'public_daily_realized_attribution'>>(
        'public_daily_realized_attribution',
        (sb) =>
          sb
            .from(PUBLIC_REALIZED_ATTRIBUTION_VIEW)
            .select('*')
            .gte('date', fromDate)
            .order('date', { ascending: false })
            .order('ticker', { ascending: true })
            .range(from, to)
      )
  );
}

export async function fetchObservabilityData(): Promise<ObservabilityData> {
  // Distinguish a total misconfiguration (no Supabase env) from a configured-but-empty book:
  // throw so the page shows a clear error, matching the main data layer (lib/queries.ts).
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY). ' +
        'Observability data cannot be loaded.'
    );
  }
  return { decisions: await fetchDecisionHistory() };
}

// Raised from 30 with migration 065 (#1762). The view now returns ONE ROW PER RETRY ATTEMPT,
// so a date that took three attempts consumes three slots instead of one. At 30 the timeline
// would show proportionally fewer distinct dates the moment retries became visible — and
// retries are not rare: 28 of the 54 rows extant at migration time were collapsed multi-attempt
// writes. 90 preserves ~30 distinct dates even if every one of them exhausts MAX_OUTER_ATTEMPTS.
const RUN_DIAGNOSTICS_LIMIT = 90;

/**
 * Read run health from the anon-readable `atlas_run_health` view (migration 041).
 * Cost/tokens/grounding fields are null on the public dashboard — the view
 * deliberately omits operator-internal spend telemetry. Fail-soft: empty array
 * on missing source / RLS deny.
 */
export async function fetchResearchRunDiagnostics(): Promise<ResearchRunDiagnostics[]> {
  const res = await safeSelect<ViewRow<'atlas_run_health'>>('atlas_run_health', (sb) =>
    sb
      .from('atlas_run_health')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(RUN_DIAGNOSTICS_LIMIT)
  );
  return res.rows.map((r) => ({
    run_id: r.run_id,
    // `?? null` rather than `?? 1`: a row written before migration 065 carries 0, and a row
    // read from an un-migrated view carries undefined. Both mean "unknown", and defaulting
    // either to 1 would fabricate the provenance #1762 exists to stop fabricating.
    attempt: r.attempt ?? null,
    run_type: r.run_type,
    run_date: r.run_date,
    model: r.model,
    status: r.status,
    started_at: r.started_at,
    finished_at: r.finished_at,
    duration_s: r.duration_s,
    llm_calls: null,
    prompt_tokens: null,
    completion_tokens: null,
    total_tokens: null,
    cached_tokens: null,
    search_calls: null,
    grounding_ok: null,
    grounding_failed: null,
    est_cost_usd: null,
    segments_total: r.segments_total,
    segments_ok: r.segments_ok,
    segments_carried: r.segments_carried,
    segments_failed: r.segments_failed,
    error_summary: null,
    breakdown: null,
    created_at: r.created_at,
  }));
}

/* ── Performance tear sheet (Pillar 3C) ───────────────────────────────────────
  Reads persisted portfolio returns and stored attribution windows. Missing
  cumulative-return fields fall back to the same deterministic first/last
  history calculation used by the backend writer. */

/** Keep only the rows whose date equals the most recent date present. */
function latestDateRows<T extends { date: string | null }>(rows: T[]): { rows: T[]; date: string | null } {
  const date = rows.reduce<string | null>(
    (m, r) => (r.date && (m === null || r.date > m) ? r.date : m),
    null
  );
  return { rows: date === null ? [] : rows.filter((r) => r.date === date), date };
}

export function buildPortfolioAttributionData(args: {
  attribution: TableRow<'position_attribution'>[];
  decisions: TableRow<'decision_log'>[];
}): PortfolioAttributionData {
  const latestAttribution = latestDateRows(args.attribution);
  return {
    attribution: latestAttribution.rows,
    attributionDate: latestAttribution.date,
    decisions: args.decisions,
  };
}

export async function fetchPortfolioAttribution(): Promise<PortfolioAttributionData> {
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY). ' +
        'Portfolio attribution cannot be loaded.'
    );
  }

  const [attributionRes, observability] = await Promise.all([
    safeSelect<TableRow<'position_attribution'>>('position_attribution', (sb) =>
      sb
        .from('position_attribution')
        .select('*')
        .order('date', { ascending: false })
        .limit(ATTRIBUTION_LIMIT)
    ),
    fetchObservabilityData(),
  ]);
  return buildPortfolioAttributionData({
    attribution: attributionRes.rows,
    decisions: observability.decisions,
  });
}

function latestAttributionByTicker(
  rows: TableRow<'position_attribution'>[]
): Map<string, TableRow<'position_attribution'>> {
  const latest = new Map<string, TableRow<'position_attribution'>>();
  for (const row of [...rows].sort((a, b) => b.date.localeCompare(a.date))) {
    const ticker = row.ticker.toUpperCase();
    if (!isCashTicker(ticker) && !latest.has(ticker)) latest.set(ticker, row);
  }
  return latest;
}

function finitePositive(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value) || value <= 0) return null;
  return value;
}

/** Desk unrealized % vs average entry — fail closed without basis or mark. */
function unrealizedReturnPctFromPosition(
  position: TableRow<'positions'> | null
): number | null {
  if (!position) return null;
  const stored = position.unrealized_pnl_pct ?? position.since_entry_return_pct ?? null;
  if (stored != null && Number.isFinite(stored)) return roundPct(stored);
  const entry = finitePositive(position.entry_price);
  const mark = finitePositive(position.current_price);
  if (entry == null || mark == null) return null;
  return roundPct((mark / entry - 1) * 100);
}

/** Latest positive close per ticker (marks sorted newest-first or any order). */
function latestCloseByTicker(
  marks: Array<{ ticker: string; date: string; close: number }>
): Map<string, { date: string; close: number }> {
  const latest = new Map<string, { date: string; close: number }>();
  for (const row of [...marks].sort((a, b) => b.date.localeCompare(a.date))) {
    const ticker = row.ticker.toUpperCase();
    const close = finitePositive(row.close);
    if (!close || latest.has(ticker)) continue;
    latest.set(ticker, { date: row.date, close });
  }
  return latest;
}

/**
 * When the nightly metrics refresh did not stamp `current_price` /
 * `unrealized_pnl_pct` (sync-only book rows), fill the mark from the market API
 * (fetchMarketCloses)
 * so open-book unrealized can derive from entry vs close. Never invent a mark.
 */
function applyHoldingMarks(
  position: TableRow<'positions'>,
  marksByTicker: Map<string, { date: string; close: number }>
): TableRow<'positions'> {
  if (
    (position.unrealized_pnl_pct != null && Number.isFinite(position.unrealized_pnl_pct)) ||
    (position.since_entry_return_pct != null && Number.isFinite(position.since_entry_return_pct))
  ) {
    return position;
  }
  if (finitePositive(position.current_price) != null) return position;
  const mark = marksByTicker.get(position.ticker.toUpperCase());
  if (!mark) return position;
  return {
    ...position,
    current_price: mark.close,
    // Provenance of the close actually used — matches refresh_performance_metrics (#1833).
    metrics_as_of: mark.date,
  };
}

function toOpenHoldingRow(
  ticker: string,
  position: TableRow<'positions'> | null,
  attribution: TableRow<'position_attribution'> | null
): PerformanceHoldingRow {
  return {
    ticker,
    category:
      attribution?.sector_bucket ?? position?.sector_bucket ?? position?.category ?? null,
    weightPct: position?.weight_pct ?? attribution?.weight_pct ?? null,
    unrealizedReturnPct: unrealizedReturnPctFromPosition(position),
    realizedReturnPct: null,
    // Prefer the position mark date over attribution — attribution can lag the live book.
    attributionDate: position?.metrics_as_of ?? position?.date ?? attribution?.date ?? null,
    disposition: null,
    eventId: null,
  };
}

function toRealizedHoldingRow(
  event: TableRow<'position_events'>,
  averageEntry: number | null,
  attribution: TableRow<'position_attribution'> | null,
  position: TableRow<'positions'> | null
): PerformanceHoldingRow {
  const disposition: PerformanceHoldingRow['disposition'] =
    event.event === 'TRIM' ? 'TRIM' : 'EXIT';
  return {
    ticker: event.ticker.toUpperCase(),
    category:
      attribution?.sector_bucket ?? position?.sector_bucket ?? position?.category ?? null,
    weightPct: soldWeightPct(event),
    unrealizedReturnPct: null,
    realizedReturnPct: realizedReturnVsAverageEntry(event.price, averageEntry),
    attributionDate: event.date,
    disposition,
    eventId: event.id,
  };
}

function periodReturnPct(values: number[]): number | null {
  if (values.length < 2) return null;
  const first = values[0];
  const last = values.at(-1);
  if (last == null || first <= 0 || !Number.isFinite(first) || !Number.isFinite(last)) {
    return null;
  }
  return roundPct((last / first - 1) * 100);
}

/** Gaps up to this many calendar days are non-trading stretches (weekend/holiday). */
const CONTINUITY_MAX_FILL_DAYS = 4;

function nextIsoDate(date: string): string {
  const [year, month, day] = date.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day + 1)).toISOString().slice(0, 10);
}

function calendarDaysBetween(start: string, end: string): number {
  return Math.round(
    (Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86_400_000
  );
}

/**
 * Plot-ready NAV series for the tearsheet + Brief charts (#4014).
 *
 * Chains the accounting source runs onto one base-100 index (see
 * {@link chainNavContinuity}) and forward-fills calendar gaps of up to
 * `CONTINUITY_MAX_FILL_DAYS` from the last index value, so weekends and
 * holidays stay continuous; longer gaps are missing book runs and are left as
 * a jump rather than invented flat days.
 */
function buildContinuityNavSeries(rows: ReadonlyArray<NavContinuityRow>): PortfolioReturnPoint[] {
  const chained = chainNavContinuity(rows);
  if (chained.length === 0) return [];
  const points: PortfolioReturnPoint[] = [];
  for (let position = 0; position < chained.length; position += 1) {
    const point = chained[position];
    if (position > 0) {
      const previous = chained[position - 1];
      const gap = calendarDaysBetween(previous.date, point.date);
      if (gap > 1 && gap - 1 <= CONTINUITY_MAX_FILL_DAYS) {
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

function buildBenchmarkComparisons(
  navSeries: PortfolioReturnPoint[],
  prices: Array<{ ticker?: string; date: string; close: number }>,
  fallbackTicker: string
): BenchmarkComparison[] {
  if (navSeries.length < 2) return [];
  const grouped = new Map<string, Array<{ date: string; close: number }>>();
  for (const row of prices) {
    if (!Number.isFinite(row.close) || row.close <= 0) continue;
    const ticker = (row.ticker ?? fallbackTicker).toUpperCase();
    if (!grouped.has(ticker)) grouped.set(ticker, []);
    grouped.get(ticker)!.push(row);
  }

  const order = new Map<string, number>(
    DASHBOARD_BENCHMARK_TICKERS.map((ticker, index) => [ticker, index])
  );
  return [...grouped.entries()]
    .map(([ticker, rows]): BenchmarkComparison | null => {
      const sorted = [...rows].sort((left, right) => left.date.localeCompare(right.date));
      if (sorted.length < 2) return null;
      const baseline = sorted[0].close;
      let priceIndex = -1;
      const series = navSeries.map((point) => {
        while (priceIndex + 1 < sorted.length && sorted[priceIndex + 1].date <= point.date) {
          priceIndex += 1;
        }
        const close = priceIndex >= 0 ? sorted[priceIndex].close : baseline;
        return { date: point.date, returnPct: roundPct((close / baseline - 1) * 100) };
      });
      return { ticker, returnPct: series.at(-1)!.returnPct, series };
    })
    .filter((comparison): comparison is BenchmarkComparison => comparison != null)
    .sort(
      (left, right) =>
        (order.get(left.ticker) ?? Number.MAX_SAFE_INTEGER) -
          (order.get(right.ticker) ?? Number.MAX_SAFE_INTEGER) ||
        left.ticker.localeCompare(right.ticker)
    );
}

function buildPositionContributionSeries(
  navSeries: PortfolioReturnPoint[],
  positions: TableRow<'positions'>[],
  currentTickers: Set<string>
): ContributionReturnPoint[] {
  if (!navSeries.length) return [];

  const snapshots = new Map<string, Map<string, TableRow<'positions'>>>();
  const pricesByTicker = new Map<string, Array<{ date: string; price: number }>>();
  for (const row of positions) {
    const ticker = row.ticker.toUpperCase();
    if (isCashTicker(ticker) || !currentTickers.has(ticker)) continue;
    if (!snapshots.has(row.date)) snapshots.set(row.date, new Map());
    snapshots.get(row.date)!.set(ticker, row);
    if (row.current_price != null && row.current_price > 0) {
      if (!pricesByTicker.has(ticker)) pricesByTicker.set(ticker, []);
      pricesByTicker.get(ticker)!.push({ date: row.date, price: row.current_price });
    }
  }

  const snapshotDates = [...snapshots.keys()].sort();
  const cumulativeByTicker = new Map<string, number[]>();
  for (const [ticker, rawPrices] of pricesByTicker) {
    const prices = [...rawPrices].sort((left, right) => left.date.localeCompare(right.date));
    const cumulative: number[] = [0];
    let snapshotIndex = -1;
    let priceIndex = -1;
    let priorWeight = 0;
    let priorPrice: number | null = null;
    let hasComparableInterval = false;

    for (let index = 0; index < navSeries.length; index += 1) {
      const date = navSeries[index].date;
      while (snapshotIndex + 1 < snapshotDates.length && snapshotDates[snapshotIndex + 1] <= date) {
        snapshotIndex += 1;
      }
      while (priceIndex + 1 < prices.length && prices[priceIndex + 1].date <= date) {
        priceIndex += 1;
      }

      const snapshot = snapshotIndex >= 0 ? snapshots.get(snapshotDates[snapshotIndex]) : null;
      const weight = snapshot?.get(ticker)?.weight_pct ?? 0;
      const price = priceIndex >= 0 ? prices[priceIndex].price : null;
      if (index > 0) {
        let next = cumulative[index - 1];
        if (priorPrice != null && price != null && priorPrice > 0) {
          next += priorWeight * (price / priorPrice - 1);
          hasComparableInterval = true;
        }
        cumulative.push(roundPct(next));
      }
      priorWeight = weight;
      priorPrice = price;
    }

    if (hasComparableInterval) cumulativeByTicker.set(ticker, cumulative);
  }

  return navSeries.map((point, index) => ({
    t: point.date,
    returnPct: point.returnPct,
    contributions: Object.fromEntries(
      [...cumulativeByTicker.entries()]
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([ticker, values]) => [ticker, values[index]])
    ),
  }));
}

/**
 * Upper bound on a believable single-day per-ticker contribution, in percentage
 * points (#4102). An unlevered base-100 book can in principle exceed 100 pp on a
 * >100% single-day move, so this is a sanity bound rather than an invariant:
 * rows beyond it mean the period's equity base could not anchor its P&L — the
 * 2026-08-25 tip opened on $0.10 of cash and published ±1,723 pp as a final row —
 * so they are treated as missing instead of being accumulated into every later
 * day's bar.
 */
const REALIZED_DAILY_CONTRIBUTION_LIMIT_PP = 100;

/**
 * Cumulative per-asset contribution from finalized accounting (#3956).
 *
 * `daily_realized_attribution` publishes each ticker's daily contribution in
 * percentage points — price, fees, and slippage only. Cash (dividends,
 * interest) is booked to the period's `cash_contribution` and is **not**
 * published by the view, so these bars do not reconcile to the NAV day return;
 * the difference is cash. The tearsheet still no longer depends on the position
 * marks the nightly refresh may not have written yet. Day one is the base (0),
 * matching the weight-times-mark series. Days before the first finalized row
 * render flat at 0 — the view is final-only, consistent with the current
 * accounting run the NAV line already plots. Returns no points when no row lands
 * in the plotted run (#3983): rows from a prior finalized run must not render as
 * an all-zero series that suppresses the marks fallback.
 *
 * Rows beyond {@link REALIZED_DAILY_CONTRIBUTION_LIMIT_PP} in a single day are
 * dropped as unanchored (#4102), so one degenerate period cannot inflate every
 * later cumulative bar, and `startsOn` reports the first plotted contribution so
 * the surface can say when finalized accounting begins.
 */
function buildRealizedContributionSeries(
  navSeries: PortfolioReturnPoint[],
  realized: ViewRow<'public_daily_realized_attribution'>[],
  tickers: Set<string>
): { points: ContributionReturnPoint[]; startsOn: string | null } {
  if (navSeries.length === 0 || realized.length === 0 || tickers.size === 0) {
    return { points: [], startsOn: null };
  }
  const byTicker = new Map<string, Map<string, number>>();
  for (const row of realized) {
    const ticker = row.ticker.toUpperCase();
    if (!tickers.has(ticker)) continue;
    const value = row.contribution_pct;
    if (value == null || !Number.isFinite(value)) continue;
    if (Math.abs(value) > REALIZED_DAILY_CONTRIBUTION_LIMIT_PP) continue;
    let byDate = byTicker.get(ticker);
    if (!byDate) {
      byDate = new Map<string, number>();
      byTicker.set(ticker, byDate);
    }
    byDate.set(row.date, value);
  }
  if (byTicker.size === 0) return { points: [], startsOn: null };
  const cumulativeByTicker = new Map<string, number[]>();
  let hasPlottedContribution = false;
  let startsOn: string | null = null;
  for (const [ticker, byDate] of byTicker) {
    const cumulative: number[] = [];
    let running = 0;
    navSeries.forEach((point, index) => {
      // Index 0 is the base row (always 0) — never counts as coverage.
      const contribution = index > 0 ? byDate.get(point.date) : undefined;
      if (contribution != null) {
        running += contribution;
        hasPlottedContribution = true;
        if (startsOn === null || point.date < startsOn) startsOn = point.date;
      }
      cumulative.push(roundPct(running));
    });
    cumulativeByTicker.set(ticker, cumulative);
  }
  // Rows from a prior finalized run can sit entirely before the plotted window
  // (e.g. across a trailing seam). All-zero cumulatives would then suppress the
  // marks accrual and present missing attribution as a flat zero — leave the
  // realized source unusable so the caller falls back.
  if (!hasPlottedContribution) return { points: [], startsOn: null };
  return {
    points: navSeries.map((point, index) => ({
      t: point.date,
      returnPct: point.returnPct,
      contributions: Object.fromEntries(
        [...cumulativeByTicker.entries()]
          .sort(([left], [right]) => left.localeCompare(right))
          .map(([ticker, values]) => [ticker, values[index]])
      ),
    })),
    startsOn,
  };
}

function latestPositionByTicker(
  positions: TableRow<'positions'>[]
): Map<string, TableRow<'positions'>> {
  const latest = new Map<string, TableRow<'positions'>>();
  for (const position of [...positions].sort((a, b) => b.date.localeCompare(a.date))) {
    const ticker = position.ticker.toUpperCase();
    if (!isCashTicker(ticker) && !latest.has(ticker)) latest.set(ticker, position);
  }
  return latest;
}

/** Ledger sells only — EXIT (full) and TRIM (partial). One row per fill event. */
function realizedSellEvents(
  events: TableRow<'position_events'>[]
): TableRow<'position_events'>[] {
  return events.filter((event) => event.event === 'EXIT' || event.event === 'TRIM');
}

export function buildPerformanceTearsheet(args: {
  nav: TableRow<'nav_history'>[];
  positions: TableRow<'positions'>[];
  metrics: TableRow<'portfolio_metrics'> | null;
  attribution: TableRow<'position_attribution'>[];
  /** Finalized per-ticker daily contribution rows from the public view (#3956). */
  realizedAttribution?: ViewRow<'public_daily_realized_attribution'>[];
  /** True when that read errored or hit the paging cap (#3983). */
  realizedAttributionDegraded?: boolean;
  events?: TableRow<'position_events'>[];
  benchmarkPrices?: Array<{ ticker?: string; date: string; close: number }>;
  /** Latest closes for open-book tickers when positions rows lack marks. */
  holdingMarks?: Array<{ ticker: string; date: string; close: number }>;
  /** Raw accounting rows (with contract) for SSOT badges (#3580). */
  accountingNav?: AccountingNavRow[];
  /** Committed snapshot date for book-as-of SSOT. */
  snapshotDate?: string | null;
}): PerformanceTearsheet {
  const navAsc = [...args.nav].sort((a, b) => a.date.localeCompare(b.date));
  // #3767 / #4014: carry the curated seam marker (and day return) onto every
  // plotted row, then chain the runs — never bridge legacy estimates to
  // finalized accounting (the false Sep-8 ~+10% jump), never hide the history.
  const seamByDate = new Map(
    (args.accountingNav ?? []).map((row) => [
      row.date,
      {
        source: row.source,
        series_seam: row.series_seam === true,
        day_return_pct: row.day_return_pct ?? null,
      },
    ])
  );
  const navSeries = buildContinuityNavSeries(
    navAsc.map((row) => {
      const seam = seamByDate.get(row.date);
      return {
        date: row.date,
        nav: row.nav,
        source: seam?.source ?? null,
        series_seam: seam?.series_seam ?? false,
        day_return_pct: seam?.day_return_pct ?? null,
      };
    })
  );
  // Chained across runs, so the chart and the since-inception KPI agree.
  const inceptionDate = navSeries[0]?.date ?? navAsc[0]?.date ?? null;
  const currentSnapshot = latestDateRows(args.positions);
  const marksByTicker = latestCloseByTicker(args.holdingMarks ?? []);
  const currentPositions = currentSnapshot.rows
    .filter((position) => !isCashTicker(position.ticker) && position.weight_pct > 0)
    .map((position) => applyHoldingMarks(position, marksByTicker));
  const attributionByTicker = latestAttributionByTicker(args.attribution);
  const latestPosition = latestPositionByTicker(args.positions);
  const latestAttribution = latestDateRows(args.attribution);
  const currentTickers = new Set(
    (currentPositions.length ? currentPositions : latestAttribution.rows)
      .filter((row) => !isCashTicker(row.ticker))
      .map((row) => row.ticker.toUpperCase())
  );
  const positionByTicker = new Map(
    currentPositions.map((position) => [position.ticker.toUpperCase(), position])
  );
  const currentHoldings = [...currentTickers]
    .map((ticker) =>
      toOpenHoldingRow(
        ticker,
        positionByTicker.get(ticker) ?? null,
        attributionByTicker.get(ticker) ?? null
      )
    )
    .sort((a, b) => (b.weightPct ?? 0) - (a.weightPct ?? 0));
  // Realized section = ledger EXIT + TRIM fills (including trims while still held).
  // Do not synthesize closed rows from attribution ghosts — that invented P&L without fills.
  const historicalHoldings = realizedSellEvents(args.events ?? [])
    .map((event) => {
      const ticker = event.ticker.toUpperCase();
      return toRealizedHoldingRow(
        event,
        averageEntryAsOf(args.positions, ticker, event.date),
        attributionByTicker.get(ticker) ?? null,
        latestPosition.get(ticker) ?? null
      );
    })
    .sort(
      (a, b) =>
        (b.attributionDate ?? '').localeCompare(a.attributionDate ?? '') ||
        a.ticker.localeCompare(b.ticker) ||
        Math.abs(b.realizedReturnPct ?? 0) - Math.abs(a.realizedReturnPct ?? 0)
    );
  // Accounting NAV series is the single source of truth for since-inception %.
  // Prefer derived over persisted metrics so a stale/wrong net_return_pct cannot
  // show a positive portfolio return while the base-100 index sits under 100.
  // Use filtered navSeries (same finite/positive gate as return charts), not raw navAsc.
  const derivedNetReturnPct = periodReturnPct(navSeries.map((row) => row.nav));
  const persistedBenchmarkTicker = args.metrics?.benchmark_ticker ?? 'SPY';
  const benchmarkComparisons = buildBenchmarkComparisons(
    navSeries,
    args.benchmarkPrices ?? [],
    persistedBenchmarkTicker
  );
  const defaultComparison =
    benchmarkComparisons.find((comparison) => comparison.ticker === 'SPY') ??
    benchmarkComparisons.find((comparison) => comparison.ticker === persistedBenchmarkTicker) ??
    benchmarkComparisons[0];
  const derivedBenchmarkReturnPct = defaultComparison?.returnPct ?? null;
  const netReturnPct = derivedNetReturnPct ?? args.metrics?.net_return_pct ?? null;
  const benchmarkReturnPct =
    derivedBenchmarkReturnPct ?? args.metrics?.benchmark_return_pct ?? null;
  const relativeReturnPct =
    netReturnPct != null && benchmarkReturnPct != null
      ? roundPct(netReturnPct - benchmarkReturnPct)
      : args.metrics?.relative_return_pct ?? null;
  const persistedUsed = [
    args.metrics?.net_return_pct,
    args.metrics?.benchmark_return_pct,
    args.metrics?.relative_return_pct,
  ].some((value) => value != null);
  // Derived wins for portfolio return whenever the NAV series can produce one.
  const derivedUsed = derivedNetReturnPct != null || derivedBenchmarkReturnPct != null;
  const returnsSource = persistedUsed
    ? derivedUsed
      ? 'mixed'
      : 'persisted'
    : derivedUsed
      ? 'derived'
      : 'unavailable';

  const metricsAsOf = args.metrics?.as_of_date ?? args.metrics?.date ?? null;
  const holdingsAsOf = currentSnapshot.date ?? latestAttribution.date;
  const ssot = attachTearsheetSsot({
    accountingNav: args.accountingNav,
    navHistory: navAsc,
    metricsAsOf: args.metrics?.as_of_date ?? args.metrics?.date ?? null,
    snapshotDate: args.snapshotDate ?? null,
    positions: args.positions,
    holdingsAsOf,
  });
  const realized = buildRealizedContributionSeries(
    navSeries,
    args.realizedAttribution ?? [],
    currentTickers
  );
  const realizedSeries = realized.points;
  const contributionSource: PerformanceContributionSource = realizedSeries.length
    ? args.realizedAttributionDegraded
      ? 'realized_truncated'
      : 'realized'
    : args.realizedAttributionDegraded
      ? 'marks_degraded'
      : 'marks';

  return {
    currentNav: navAsc.at(-1)?.nav ?? null,
    netReturnPct,
    benchmarkReturnPct,
    relativeReturnPct,
    benchmarkTicker: defaultComparison?.ticker ?? persistedBenchmarkTicker,
    benchmarkComparisons,
    returnsSource,
    metricsAsOf,
    inceptionDate,
    holdingsAsOf,
    generatedAt: args.metrics?.generated_at ?? null,
    navSeries,
    contributionSeries: realizedSeries.length
      ? realizedSeries
      : buildPositionContributionSeries(navSeries, args.positions, currentTickers),
    contributionSource,
    contributionStartsOn: realizedSeries.length ? realized.startsOn : null,
    currentHoldings,
    historicalHoldings,
    ...ssot,
  };
}

function attachTearsheetSsot(args: {
  accountingNav?: AccountingNavRow[];
  navHistory: TableRow<'nav_history'>[];
  metricsAsOf: string | null;
  snapshotDate: string | null;
  positions: TableRow<'positions'>[];
  holdingsAsOf: string | null;
}): Pick<PerformanceTearsheet, 'navContract' | 'metricsLagging' | 'tipInvestedPct'> {
  const bookAsOf = committedBookDate(args.snapshotDate, args.positions.map((p) => p.date));
  const openBookDate = bookAsOf ?? args.holdingsAsOf;
  const openBook = openBookDate
    ? args.positions.filter((p) => p.date === openBookDate && !isCashTicker(p.ticker))
    : [];
  const navRows: AccountingNavRow[] =
    args.accountingNav ??
    args.navHistory.map((row) => ({
      date: row.date,
      nav: row.nav,
      cash_pct: row.cash_pct ?? null,
      invested_pct: row.invested_pct ?? null,
      day_return_pct: null,
      source: 'legacy_nav_history',
      contract: 'legacy_estimate',
    }));
  const meta = buildPerformanceSsotMeta({
    navRows,
    metricsAsOf: args.metricsAsOf,
    snapshotDate: args.snapshotDate,
    positionDates: args.positions.map((p) => p.date),
    positionMetricsAsOf: openBook.map((p) => p.metrics_as_of ?? null),
    metricsInvestedPct: null,
  });
  return {
    navContract: meta.navContract,
    metricsLagging: meta.metricsLagging,
    tipInvestedPct: meta.tipInvestedPct,
  };
}

/** Shared Brief + Tearsheet performance payload (#3580). */
export type PerformanceBundle = {
  tearsheet: PerformanceTearsheet;
  ssot: PerformanceSsotMeta;
};

/**
 * Single performance fetch for Tearsheet and Brief persisted KPIs.
 * Prefer this over calling {@link fetchPerformanceTearsheet} alone — same NAV
 * adapter, contract badge, and metrics-lag chrome.
 */
export async function getPerformanceBundle(
  opts: { snapshotDate?: string | null } = {}
): Promise<PerformanceBundle> {
  if (!isSupabaseConfigured() || !supabase) {
    const tearsheet = buildPerformanceTearsheet({
      nav: [],
      positions: [],
      metrics: null,
      attribution: [],
      events: [],
      snapshotDate: opts.snapshotDate ?? null,
    });
    return {
      tearsheet,
      ssot: buildPerformanceSsotMeta({
        navRows: [],
        metricsAsOf: null,
        snapshotDate: opts.snapshotDate ?? null,
        positionDates: [],
        positionMetricsAsOf: [],
      }),
    };
  }

  let snapshotDate = opts.snapshotDate ?? null;
  if (snapshotDate == null) {
    const snapRes = await supabase
      .from('daily_snapshots')
      .select('date')
      .order('date', { ascending: false })
      .limit(1)
      .maybeSingle();
    if (!snapRes.error) {
      snapshotDate = (snapRes.data as { date?: string | null } | null)?.date ?? null;
    }
  }

  const navQuery = await supabase
    .from(ACCOUNTING_NAV_VIEW)
    .select('date,nav,cash_pct,invested_pct,day_return_pct,source,contract,series_seam')
    .order('date', { ascending: true })
    .limit(PERFORMANCE_HISTORY_LIMIT);
  if (navQuery.error) {
    throw new AccountingNavContractError(navQuery.error);
  }
  const navRows = (navQuery.data ?? []) as AccountingNavRow[];

  const [positionsRes, metricsRes, attributionRes, realizedRes, eventsRes] = await Promise.all([
    safeSelect<TableRow<'positions'>>('positions', (sb) =>
      houseBook(sb, 'positions')
        .order('date', { ascending: false })
        .limit(PERFORMANCE_HISTORY_LIMIT)
    ),
    safeSelect<TableRow<'portfolio_metrics'>>('portfolio_metrics', (sb) =>
      houseBook(sb, 'portfolio_metrics').order('date', { ascending: false }).limit(1)
    ),
    safeSelect<TableRow<'position_attribution'>>('position_attribution', (sb) =>
      sb
        .from('position_attribution')
        .select('*')
        .order('date', { ascending: false })
        .limit(ATTRIBUTION_LIMIT)
    ),
    navRows.length
      ? fetchRealizedAttribution(navRows[0].date)
      : Promise.resolve({ rows: [], ok: true as const, truncated: false }),
    safeSelect<TableRow<'position_events'>>('position_events', (sb) =>
      houseBook(sb, 'position_events')
        .in('event', ['EXIT', 'TRIM'])
        .order('date', { ascending: false })
        .limit(PERFORMANCE_HISTORY_LIMIT)
    ),
  ]);

  if (realizedRes.truncated) {
    console.error(
      `Supabase public_daily_realized_attribution hit the ${ATTRIBUTION_MAX_ROWS}-row ` +
        'paging cap; contribution bars may understate older days.'
    );
  }

  const navHistory: TableRow<'nav_history'>[] = navRows.map((row) => {
    const shaped = accountingNavToHistoryShape(row);
    return {
      date: shaped.date,
      nav: shaped.nav,
      cash_pct: shaped.cash_pct,
      invested_pct: shaped.invested_pct,
    };
  });
  const navWindow = [...navHistory]
    .filter((row) => Number.isFinite(row.nav) && row.nav > 0)
    .sort((left, right) => left.date.localeCompare(right.date));
  const currentBook = latestDateRows(positionsRes.rows);
  const openTickers = [
    ...new Set(
      currentBook.rows
        .filter((row) => !isCashTicker(row.ticker) && row.weight_pct > 0)
        .map((row) => row.ticker.toUpperCase())
    ),
  ];
  // Marks share the plotted NAV window: the market API answers a date window
  // (#4053, R2-only — no Supabase fallback).
  const markWindowFloor = navWindow[0]?.date ?? '';
  const markWindowCeiling = navWindow.at(-1)?.date ?? '';
  const [benchmarkMap, holdingMarksRes] = await Promise.all([
    navWindow.length >= 2
      ? fetchComparablePriceHistory(
          [...DASHBOARD_BENCHMARK_TICKERS],
          markWindowFloor,
          markWindowCeiling
        )
      : Promise.resolve({} as BenchmarkHistoryMap),
    openTickers.length
      ? fetchMarketCloses(openTickers, markWindowFloor, markWindowCeiling).then((rows) => ({
          rows,
          ok: true as const,
        }))
      : Promise.resolve({ rows: [], ok: true as const }),
  ]);
  const benchmarkPrices = Object.entries(benchmarkMap).flatMap(([ticker, series]) =>
    (series?.history ?? []).map((point) => ({
      ticker,
      date: point.date,
      close: point.price,
    }))
  );

  const metricsRow = metricsRes.rows[0] ?? null;
  const tearsheet = buildPerformanceTearsheet({
    nav: navHistory,
    positions: positionsRes.rows,
    metrics: metricsRow,
    attribution: attributionRes.rows,
    realizedAttribution: realizedRes.rows,
    realizedAttributionDegraded: !realizedRes.ok || realizedRes.truncated,
    events: eventsRes.rows,
    benchmarkPrices,
    holdingMarks: holdingMarksRes.rows,
    accountingNav: navRows,
    snapshotDate,
  });

  const openBook = currentBook.rows.filter((p) => !isCashTicker(p.ticker));
  const bookWeightInvestedPct = openBook.reduce((sum, p) => sum + Number(p.weight_pct ?? 0), 0);
  const ssot = buildPerformanceSsotMeta({
    navRows,
    metricsAsOf: metricsRow?.as_of_date ?? metricsRow?.date ?? null,
    snapshotDate,
    positionDates: positionsRes.rows.map((p) => p.date),
    positionMetricsAsOf: openBook.map((p) => p.metrics_as_of ?? null),
    bookWeightInvestedPct,
    metricsInvestedPct: metricsRow?.invested_pct != null ? Number(metricsRow.invested_pct) : null,
  });

  return { tearsheet, ssot };
}

/** @deprecated Prefer {@link getPerformanceBundle} — same NAV adapter (#3580). */
export async function fetchPerformanceTearsheet(
  opts: { snapshotDate?: string | null } = {}
): Promise<PerformanceTearsheet> {
  const { tearsheet } = await getPerformanceBundle(opts);
  return tearsheet;
}
