/**
 * Slice 0008 rewire: real Supabase/PostgREST + market-API source implementing
 * every slice dep interface (`EnvelopeSource`, `BriefDeps`, `PerformanceDeps`,
 * `LiveDeps`, `BenchmarksDeps`, `LedgerBook`).
 *
 * Replaces the `./stubs` test doubles in production. Fail-closed: any
 * upstream non-OK (Supabase/PostgREST) throws `UpstreamError`, which the route
 * layer maps to the contract §2 `upstream_empty` (502) envelope — never a
 * silent stub fallback, never synthesized data.
 *
 * Market closes are R2-API-only (no Supabase fallback, per #4053): when
 * `MARKET_DATA_URL` is unset, or a batch fails, closes resolve to an empty
 * map and the builders flow the honest-empty path (same as the dashboard
 * client `fetchMarketCloses` precedent).
 *
 * Reads mirror `apps/dashboard/lib/queries.ts` (`getFullDashboardData`):
 * `daily_snapshots` tip, house-pinned `positions` / `position_events` /
 * `portfolio_metrics`, the `public_accounting_nav_history` view, and
 * `GET /v1/market/closes` over the NAV window. No secrets leave this file —
 * the service-role key arrives via worker `env` only.
 */

import type { AllocationPositionInput, MarketCloseFill } from './allocations';
import type { PortfolioNavTipInput } from './portfolio';
import type { BriefBook, BriefDeps } from './brief';
import type { BenchmarksBook, BenchmarksDeps } from './benchmarks';
import type { PerformanceBook, PerformanceDeps, PerformanceWindow } from './performance';
import type { LiveBook, LiveDeps } from './kpis-live';
import type { LedgerBook } from './ledger';
import type { NavRowInput } from './ssot';
import type { CommittedBookSnapshot, EnvelopeSource } from './envelope';

export const HOUSE_WORKSPACE_ID = '6b753576-ced9-5319-9bfa-c5d0aacd9319' as const;

const POSITIONS_PAGE = 5000;
const MAX_TICKERS_PER_REQUEST = 25;

export interface SupabaseEnv {
  SUPABASE_URL?: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
  MARKET_DATA_URL?: string;
}

/** True when the worker can serve real reads (else the caller keeps stubs). */
export function hasSupabaseEnv(env: SupabaseEnv): boolean {
  return Boolean(env.SUPABASE_URL?.trim()) && Boolean(env.SUPABASE_SERVICE_ROLE_KEY?.trim());
}

/** Upstream failure — the route layer maps this to `upstream_empty` (502). */
export class UpstreamError extends Error {
  readonly status: number;
  readonly upstreamBody: string;
  constructor(message: string, status: number, upstreamBody: string) {
    super(message);
    this.name = 'UpstreamError';
    this.status = status;
    this.upstreamBody = upstreamBody;
  }
}

function restBase(env: SupabaseEnv): string {
  return `${env.SUPABASE_URL!.trim().replace(/\/+$/, '')}/rest/v1`;
}

/** PostgREST GET with the service-role key. Non-OK throws `UpstreamError`. */
export async function supaGet(env: SupabaseEnv, path: string): Promise<unknown> {
  const res = await fetch(`${restBase(env)}/${path}`, {
    headers: {
      apikey: env.SUPABASE_SERVICE_ROLE_KEY!,
      Authorization: `Bearer ${env.SUPABASE_SERVICE_ROLE_KEY!}`,
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new UpstreamError(`supabase ${res.status} for ${path.split('?')[0]}`, res.status, body);
  }
  return res.json() as Promise<unknown>;
}

function num(value: unknown): number | null {
  if (value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function str(value: unknown): string | null {
  if (value == null) return null;
  const s = String(value);
  return s.length > 0 ? s : null;
}

interface SnapshotTip {
  date: string;
}

async function loadSnapshotDate(env: SupabaseEnv, asOf: string | null): Promise<string | null> {
  const asOfFilter = asOf == null ? '' : `&date=lte.${encodeURIComponent(asOf)}`;
  const rows = (await supaGet(
    env,
    `daily_snapshots?select=date&order=date.desc&limit=1${asOfFilter}`,
  )) as SnapshotTip[];
  return rows.length > 0 ? rows[0].date : null;
}

interface PositionRow {
  date: string;
  ticker: string;
  weight_pct?: number | string | null;
  entry_price?: number | string | null;
  current_price?: number | string | null;
  unrealized_pnl_pct?: number | string | null;
  since_entry_return_pct?: number | string | null;
  metrics_as_of?: string | null;
}

async function loadAllPositions(env: SupabaseEnv): Promise<PositionRow[]> {
  return (await supaGet(
    env,
    `positions?select=*&workspace_id=eq.${HOUSE_WORKSPACE_ID}&order=date.desc&limit=${POSITIONS_PAGE}`,
  )) as PositionRow[];
}

/** Latest position date on or before the snapshot; else null. */
export function committedDate(snapshotDate: string | null, dates: readonly string[]): string | null {
  if (!snapshotDate) return null;
  let best: string | null = null;
  for (const d of dates) {
    if (d <= snapshotDate && (best === null || d > best)) best = d;
  }
  return best;
}

interface NavViewRow {
  date: string;
  nav?: number | string | null;
  cash_pct?: number | string | null;
  invested_pct?: number | string | null;
  day_return_pct?: number | string | null;
  source?: string | null;
  contract?: string | null;
  series_seam?: boolean | null;
}

async function loadNavRows(env: SupabaseEnv): Promise<NavRowInput[]> {
  const rows = (await supaGet(
    env,
    `public_accounting_nav_history?select=date,nav,cash_pct,invested_pct,day_return_pct,source,contract,series_seam&order=date.asc&limit=5000`,
  )) as NavViewRow[];
  return rows.map((r) => ({
    date: r.date,
    nav: num(r.nav) ?? 0,
    invested_pct: num(r.invested_pct),
    cash_pct: num(r.cash_pct),
    day_return_pct: num(r.day_return_pct),
    source: str(r.source),
    contract: str(r.contract),
    series_seam: r.series_seam === true,
  }));
}

interface MetricsRow {
  date?: string | null;
  as_of_date?: string | null;
  invested_pct?: number | string | null;
}

async function loadMetrics(env: SupabaseEnv): Promise<{ investedPct: number | null; asOf: string | null }> {
  const rows = (await supaGet(
    env,
    `portfolio_metrics?select=date,as_of_date,invested_pct&workspace_id=eq.${HOUSE_WORKSPACE_ID}&order=date.desc&limit=1`,
  )) as MetricsRow[];
  if (rows.length === 0) return { investedPct: null, asOf: null };
  return { investedPct: num(rows[0].invested_pct), asOf: str(rows[0].as_of_date ?? rows[0].date) };
}

function toAllocationPosition(p: PositionRow): AllocationPositionInput {
  return {
    ticker: p.ticker,
    weightActual: num(p.weight_pct),
    entryPrice: num(p.entry_price),
    currentPrice: num(p.current_price),
    unrealizedPnlPct: num(p.unrealized_pnl_pct),
    sinceEntryReturnPct: num(p.since_entry_return_pct),
    metricsAsOf: str(p.metrics_as_of),
  };
}

function toNavTipInput(r: NavRowInput): PortfolioNavTipInput {
  return {
    date: r.date,
    nav: r.nav,
    investedPct: r.invested_pct ?? null,
    cashPct: r.cash_pct ?? null,
    dayReturnPct: r.day_return_pct ?? null,
    source: r.source,
    contract: r.contract,
    seriesSeam: r.series_seam ?? false,
  };
}

async function loadCommittedBook(
  env: SupabaseEnv,
  asOf: string | null,
): Promise<CommittedBookSnapshot | null> {
  const snapshotDate = await loadSnapshotDate(env, asOf);
  if (snapshotDate == null) return null;
  const all = await loadAllPositions(env);
  const dates = [...new Set(all.map((p) => p.date))];
  const bookAsOf = committedDate(snapshotDate, dates);
  if (bookAsOf == null) return null;
  const [navRows, metrics] = await Promise.all([loadNavRows(env), loadMetrics(env)]);
  return {
    snapshotDate,
    bookAsOf,
    positionDates: dates,
    positions: all.filter((p) => p.date === bookAsOf).map(toAllocationPosition),
    navRows: navRows.map(toNavTipInput),
    metricsInvestedPct: metrics.investedPct,
    metricsAsOf: metrics.asOf,
  };
}

// --- Market API (R2-only closes) --------------------------------------------

function marketBase(env: SupabaseEnv): string {
  return (env.MARKET_DATA_URL ?? '').trim().replace(/\/+$/, '');
}

interface MarketCloseRow {
  date: string;
  ticker: string;
  close: number;
}

/** R2-API-only closes; empty map when unset or on any batch failure. */
export async function loadMarketClosesMap(
  env: SupabaseEnv,
  tickers: readonly string[],
  from: string,
  to: string,
): Promise<ReadonlyMap<string, MarketCloseFill>> {
  const out = new Map<string, MarketCloseFill>();
  const base = marketBase(env);
  if (!base || tickers.length === 0) return out;
  const uniq = [...new Set(tickers)];
  try {
    for (let i = 0; i < uniq.length; i += MAX_TICKERS_PER_REQUEST) {
      const batch = uniq.slice(i, i + MAX_TICKERS_PER_REQUEST);
      const query = `tickers=${batch.map((t) => encodeURIComponent(t)).join(',')}&from=${from}&to=${to}`;
      const res = await fetch(`${base}/v1/market/closes?${query}`);
      if (!res.ok) return new Map();
      const body = (await res.json()) as { rows?: MarketCloseRow[] };
      for (const row of body.rows ?? []) {
        const price = Number(row.close);
        if (!Number.isFinite(price)) continue;
        const prev = out.get(row.ticker);
        if (!prev || row.date >= prev.asOf) out.set(row.ticker, { price, asOf: row.date });
      }
    }
  } catch {
    return new Map();
  }
  return out;
}

async function loadMarketUniverse(env: SupabaseEnv): Promise<string[] | null> {
  const base = marketBase(env);
  if (!base) return null;
  try {
    const res = await fetch(`${base}/v1/market/tickers`);
    if (!res.ok) return null;
    const body = (await res.json()) as { tickers?: string[] };
    return Array.isArray(body.tickers) ? body.tickers : null;
  } catch {
    return null;
  }
}

// --- Source factory ---------------------------------------------------------

export interface SupabaseSource {
  envelope: EnvelopeSource;
  brief: BriefDeps;
  performance: PerformanceDeps;
  live: LiveDeps;
  benchmarks: BenchmarksDeps;
  ledger: LedgerBook;
}

interface LedgerEventRow {
  date: string;
  ticker: string;
  event: string;
  weight_pct?: number | string | null;
  prev_weight_pct?: number | string | null;
}

function navWindow(rows: NavRowInput[]): { from: string; to: string } | null {
  if (rows.length === 0) return null;
  const dates = rows.map((r) => r.date).sort();
  return { from: dates[0], to: dates[dates.length - 1] };
}

export function createSupabaseSource(env: SupabaseEnv): SupabaseSource {
  const ledger: LedgerBook = {
    getJson: (path: string) => supaGet(env, path),
  };
  const envelope: EnvelopeSource = {
    loadBook: (asOf: string | null) => loadCommittedBook(env, asOf),
    loadMarketCloses: async (tickers: readonly string[], pin: string | null) => {
      void pin;
      const book = await loadCommittedBook(env, null);
      if (!book || book.navRows.length === 0) return new Map();
      const w = navWindow(book.navRows.map((r) => ({ date: r.date, nav: r.nav })));
      if (!w) return new Map();
      return loadMarketClosesMap(env, tickers, w.from, w.to);
    },
  };
  const brief: BriefDeps = {
    loadBriefBook: async (asOf: string | null): Promise<BriefBook | null> => {
      const book = await loadCommittedBook(env, asOf);
      if (!book) return null;
      const dayEvents = (await supaGet(
        env,
        `position_events?select=date,ticker,event,weight_pct,prev_weight_pct` +
          `&workspace_id=eq.${HOUSE_WORKSPACE_ID}&date=eq.${book.bookAsOf}` +
          `&order=date.desc&limit=500`,
      )) as LedgerEventRow[];
      const bookRows = book.positions;
      const bookWeightInvestedPct = bookRows
        .filter((p) => p.ticker !== 'CASH')
        .reduce((acc, p) => acc + (typeof p.weightActual === 'number' ? p.weightActual : 0), 0);
      return {
        navRows: book.navRows.map((r) => ({
          date: r.date,
          nav: r.nav,
          invested_pct: r.investedPct ?? null,
          cash_pct: r.cashPct ?? null,
          day_return_pct: r.dayReturnPct ?? null,
          source: r.source ?? null,
          contract: (r.contract ?? null) as string | null,
          series_seam: r.seriesSeam ?? false,
        })),
        snapshotDate: book.snapshotDate,
        positionDates: [...book.positionDates],
        positionMetricsAsOf: bookRows.map((p) => p.metricsAsOf ?? null),
        bookWeightInvestedPct,
        metricsInvestedPct: book.metricsInvestedPct,
        metricsAsOf: book.metricsAsOf,
        live: null,
        ledgerEvents: dayEvents.map((e) => ({
          date: e.date,
          ticker: e.ticker,
          event: e.event,
          weight_pct: num(e.weight_pct),
          prev_weight_pct: num(e.prev_weight_pct),
        })),
      };
    },
  };
  const performance: PerformanceDeps = {
    loadPerformanceBook: async (
      asOf: string | null,
      benchmark: string,
      _window: PerformanceWindow,
    ): Promise<PerformanceBook | null> => {
      void _window;
      const book = await loadCommittedBook(env, asOf);
      if (!book || book.navRows.length === 0) return null;
      const navRows: NavRowInput[] = book.navRows.map((r) => ({
        date: r.date,
        nav: r.nav,
        invested_pct: r.investedPct ?? null,
        cash_pct: r.cashPct ?? null,
        day_return_pct: r.dayReturnPct ?? null,
        source: r.source ?? null,
        contract: (r.contract ?? null) as string | null,
        series_seam: r.seriesSeam ?? false,
      }));
      const w = navWindow(navRows);
      const history = w == null ? [] : await loadBenchmarkHistory(env, benchmark, w.from, w.to);
      const bookWeightInvestedPct = book.positions
        .filter((pos) => pos.ticker !== 'CASH')
        .reduce(
          (acc, pos) => acc + (typeof pos.weightActual === 'number' ? pos.weightActual : 0),
          0,
        );
      return {
        navRows,
        metricsAsOf: book.metricsAsOf,
        benchmarkHistory: history,
        snapshotDate: book.snapshotDate,
        positionDates: [...book.positionDates],
        positionMetricsAsOf: book.positions.map((pos) => pos.metricsAsOf ?? null),
        bookWeightInvestedPct,
        metricsInvestedPct: book.metricsInvestedPct,
      };
    },
  };
  const live: LiveDeps = {
    loadLiveBook: async (): Promise<LiveBook | null> => {
      const book = await loadCommittedBook(env, null);
      if (!book) return null;
      const w = navWindow(book.navRows.map((r) => ({ date: r.date, nav: r.nav })));
      const history = w == null ? [] : await loadBenchmarkHistory(env, 'SPY', w.from, w.to);
      return {
        positions: book.positions
          .filter((p) => p.ticker !== 'CASH')
          .map((p) => ({
            ticker: p.ticker,
            weightPct: typeof p.weightActual === 'number' ? p.weightActual : 0,
            markPrice: p.currentPrice ?? null,
            effectivePrice: p.currentPrice ?? null,
            isLive: false,
            metricsAsOf: p.metricsAsOf ?? null,
            livePriceDate: null,
          })),
        navHistory: book.navRows.map((r) => ({ date: r.date, nav: r.nav })),
        benchmarkHistory: history,
        benchmarkTicker: 'SPY',
      };
    },
  };
  const benchmarks: BenchmarksDeps = {
    loadBenchmarksBook: async (
      from: string | null,
      to: string | null,
    ): Promise<BenchmarksBook | null> => {
      const navRows = await loadNavRows(env);
      const inWindow = navRows.filter(
        (r) => (from == null || r.date >= from) && (to == null || r.date <= to),
      );
      if (inWindow.length === 0) return null;
      const dates = inWindow.map((r) => r.date).sort();
      const universe = await loadMarketUniverse(env);
      const tickers = universe ?? [];
      const marketCloses: Record<string, { date: string; close: number }[]> = {};
      if (tickers.length > 0) {
        const base = marketBase(env);
        try {
          for (let i = 0; i < tickers.length; i += MAX_TICKERS_PER_REQUEST) {
            const batch = tickers.slice(i, i + MAX_TICKERS_PER_REQUEST);
            const query =
              `tickers=${batch.map((t) => encodeURIComponent(t)).join(',')}` +
              `&from=${dates[0]}&to=${dates[dates.length - 1]}`;
            const res = await fetch(`${base}/v1/market/closes?${query}`);
            if (!res.ok) break;
            const body = (await res.json()) as { rows?: MarketCloseRow[] };
            for (const row of body.rows ?? []) {
              const price = Number(row.close);
              if (!Number.isFinite(price)) continue;
              (marketCloses[row.ticker] ??= []).push({ date: row.date, close: price });
            }
          }
        } catch {
          // Honest-empty: builders fall back to keys, never to Supabase.
        }
      }
      return { navDates: dates, marketCloses, marketUniverse: universe };
    },
  };
  return { envelope, brief, performance, live, benchmarks, ledger };
}

async function loadBenchmarkHistory(
  env: SupabaseEnv,
  benchmark: string,
  from: string,
  to: string,
): Promise<{ date: string; price: number }[]> {
  const base = marketBase(env);
  if (!base) return [];
  try {
    const res = await fetch(
      `${base}/v1/market/closes?tickers=${encodeURIComponent(benchmark)}&from=${from}&to=${to}`,
    );
    if (!res.ok) return [];
    const body = (await res.json()) as { rows?: MarketCloseRow[] };
    return (body.rows ?? [])
      .filter((r) => Number.isFinite(Number(r.close)))
      .map((r) => ({ date: r.date, price: Number(r.close) }))
      .sort((a, b) => (a.date < b.date ? -1 : 1));
  } catch {
    return [];
  }
}
