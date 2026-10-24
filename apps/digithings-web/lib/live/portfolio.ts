/**
 * The digiquant band's live reads (#4429 round 7).
 *
 * A reduced copy of `apps/digiquant-web/lib/live/` — the same canonical backend,
 * the same tables, the same key — scoped to what this band actually draws: the
 * published NAV series, a benchmark leg from the keyless market-data Worker, and
 * the strategy library index. It deliberately does NOT copy `useLivePrices`
 * (Coinbase websocket + Supabase Realtime): the landing band shows a monthly
 * curve and period returns, not a live mark, so a socket would be cost with no
 * pixel.
 *
 * Every read degrades: with no env the client is null and each function returns
 * empty, so the band keeps its badged example series and the static export still
 * builds.
 */
import { supabase } from "./supabaseClient";

/**
 * Finalized tips only (#2599 / #3767). `public_accounting_nav_history` still
 * appends `nav_history` on any date that has no finalized row, and
 * `portfolio_materialize` still writes that table. A latest-source-run cut
 * then publishes the provisional tail — one row of it, and the landing chart
 * falls through to the synthetic example.
 */
export const ACCOUNTING_NAV_VIEW = "public_finalized_nav" as const;

/**
 * Columns on `public_finalized_nav`. That view has no `series_seam`; selecting
 * the stitched view's extra column makes PostgREST error and the read return
 * empty, which paints the example series.
 */
export const ACCOUNTING_NAV_COLUMNS =
  "date, nav, cash_pct, invested_pct, day_return_pct, source";

const FINALIZED_SOURCE = "finalized_accounting";

const STRATEGY_TABLE = "strategy_tearsheets";

/** The benchmark leg. SPY — the same ticker digiquant.io's dashboard uses. */
export const BENCHMARK_TICKER = "SPY";

export interface NavPoint {
  date: string;
  nav: number;
}

export interface PricePoint {
  date: string;
  price: number;
}

/** One strategy-library card, projected from the stored tearsheet payload. */
export interface StrategyRead {
  strategy: string;
  label: string | null;
  kind: string | null;
  symbol: string;
  periodStart: string;
  periodEnd: string;
  netProfitPct: number;
  maxDrawdownPct: number;
  profitFactor: number | null;
  winRatePct: number | null;
  totalTrades: number;
  vsLumpPct: number | null;
  allocatedPct: number | null;
}

interface AccountingNavRow {
  date: string;
  nav: number;
  source: string | null;
}

/** One PostgREST row → a point, or null when date/nav are unusable. */
export function accountingNavRow(row: unknown): AccountingNavRow | null {
  if (!row || typeof row !== "object") return null;
  const r = row as { date?: unknown; nav?: unknown; source?: unknown };
  const date = typeof r.date === "string" ? r.date : null;
  const nav = Number(r.nav);
  if (!date || !Number.isFinite(nav)) return null;
  return {
    date,
    nav,
    source: typeof r.source === "string" ? r.source : null,
  };
}

/**
 * Finalized points the band may index from its first row, oldest first.
 *
 * A labeled `legacy_nav_history` row is dropped wherever it sits: a prefix
 * would be indexed into the window return, and a provisional tip would become
 * the whole series. Rows with no source stay — `public_finalized_nav` is
 * finalized by definition, and a date/nav select does not repeat the label.
 */
export function publishedNavPoints(rows: readonly unknown[]): NavPoint[] {
  const points: NavPoint[] = [];
  for (const row of rows) {
    const parsed = accountingNavRow(row);
    if (!parsed) continue;
    if (parsed.source != null && parsed.source !== FINALIZED_SOURCE) continue;
    points.push({ date: parsed.date, nav: parsed.nav });
  }
  points.sort((a, b) => a.date.localeCompare(b.date));
  return points;
}

/** Public house-book API. Same origin digiquant.io already reads. No key. */
export const PUBLIC_DASHBOARD_API = "https://graph.digithings.ai/dashboard-api";

/** Dev preview proxy. The worker allows digithings.ai, not localhost. */
export const DEV_DASHBOARD_API = "/dashboard-api";

/**
 * The dashboard's canonical read API. An explicit `NEXT_PUBLIC_DASHBOARD_API_URL`
 * wins (local stack). Development uses the same-origin rewrite. Production uses
 * the public house book. Unit tests stay offline and empty.
 */
export function dashboardApiBase(
  env: { NEXT_PUBLIC_DASHBOARD_API_URL?: string; NODE_ENV?: string } = {
    // Direct member reads so the client bundle inlines NODE_ENV. Passing
    // `process.env` whole does not.
    NEXT_PUBLIC_DASHBOARD_API_URL: process.env.NEXT_PUBLIC_DASHBOARD_API_URL,
    NODE_ENV: process.env.NODE_ENV,
  },
): string {
  const raw = (env.NEXT_PUBLIC_DASHBOARD_API_URL ?? "").trim().replace(/\/+$/, "");
  if (raw) return raw;
  if (env.NODE_ENV === "test") return "";
  if (env.NODE_ENV === "development") return DEV_DASHBOARD_API;
  return PUBLIC_DASHBOARD_API;
}

async function getRaw(path: string): Promise<unknown> {
  const base = dashboardApiBase();
  if (!base) return null;
  try {
    const res = await fetch(`${base}${path}`, { headers: { Accept: "application/json" } });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/** House-book routes wrap rows in `{ data }`. `/v1/tables/*` returns a bare array. */
export function rowsFromDashboardBody(body: unknown): unknown[] {
  if (Array.isArray(body)) return body;
  if (body && typeof body === "object") {
    const data = (body as { data?: unknown }).data;
    if (Array.isArray(data)) return data;
  }
  return [];
}

async function getApi(path: string): Promise<unknown> {
  const body = await getRaw(path);
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  return (body as { data?: unknown }).data ?? null;
}

/**
 * `GET /nav-series` → points, oldest first. Uses the API's chained `index`
 * (its since-inception definition, DIG-2801) when present, so a bad raw `nav`
 * row (e.g. a 15.13 print on a ~102 book) cannot spike the chart; raw `nav` is
 * the fallback.
 */
export function apiNavPoints(data: unknown): NavPoint[] {
  const points = (data as { points?: unknown })?.points;
  if (!Array.isArray(points)) return [];
  const out: NavPoint[] = [];
  for (const row of points) {
    const r = row as { date?: unknown; nav?: unknown; index?: unknown };
    const index = r?.index == null ? NaN : Number(r.index);
    const nav = Number.isFinite(index) ? index : Number(r?.nav);
    if (typeof r?.date === "string" && Number.isFinite(nav)) out.push({ date: r.date, nav });
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}

/** `GET /benchmarks` → the benchmark ticker's closes from `fromDate`, oldest first. */
export function apiBenchmarkPoints(data: unknown, fromDate: string): PricePoint[] {
  const series = (data as { series?: Record<string, unknown> })?.series;
  const rows = series?.[BENCHMARK_TICKER];
  if (!Array.isArray(rows)) return [];
  const out: PricePoint[] = [];
  for (const row of rows) {
    const r = row as { date?: unknown; close?: unknown };
    const price = Number(r?.close);
    if (typeof r?.date === "string" && r.date >= fromDate && Number.isFinite(price)) {
      out.push({ date: r.date, price });
    }
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}

/** Finalized NAV points, oldest first. dashboard-api first, Supabase as before. */
export async function fetchNav(): Promise<NavPoint[]> {
  if (dashboardApiBase()) return apiNavPoints(await getApi("/nav-series"));
  if (!supabase) return [];
  const { data, error } = await supabase
    .from(ACCOUNTING_NAV_VIEW)
    .select(ACCOUNTING_NAV_COLUMNS)
    .order("date", { ascending: true });
  if (error || !data) return [];
  return publishedNavPoints(data);
}

/**
 * The benchmark leg, from the keyless R2 Worker (`GET /v1/market/closes`).
 *
 * `NEXT_PUBLIC_MARKET_DATA_URL` is the same var the price tape reads and is
 * required in prod; unset returns empty (there is deliberately no Supabase
 * fallback for prices).
 */
export async function fetchBenchmark(fromDate: string): Promise<PricePoint[]> {
  if (dashboardApiBase()) {
    return apiBenchmarkPoints(
      await getApi(`/benchmarks?tickers=${encodeURIComponent(BENCHMARK_TICKER)}`),
      fromDate,
    );
  }
  const base = (process.env.NEXT_PUBLIC_MARKET_DATA_URL ?? "").trim().replace(/\/+$/, "");
  if (!base) return [];
  const url = `${base}/v1/market/closes?tickers=${encodeURIComponent(BENCHMARK_TICKER)}&from=${encodeURIComponent(fromDate)}`;
  try {
    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) return [];
    const body = (await res.json()) as { rows?: Array<{ date?: unknown; close?: unknown }> };
    const rows = Array.isArray(body.rows) ? body.rows : [];
    return rows
      .map((row) => {
        const date = typeof row.date === "string" ? row.date : null;
        const price = Number(row.close);
        if (!date || !Number.isFinite(price)) return null;
        return { date, price };
      })
      .filter((p): p is PricePoint => p !== null)
      .sort((a, b) => a.date.localeCompare(b.date));
  } catch {
    return [];
  }
}

function toNumber(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function toStrategyRead(strategyId: string, metrics: unknown): StrategyRead | null {
  if (!metrics || typeof metrics !== "object") return null;
  const m = metrics as Record<string, unknown>;
  const symbol = typeof m.symbol === "string" ? m.symbol : "";
  const periodStart = typeof m.period_start === "string" ? m.period_start : "";
  const periodEnd = typeof m.period_end === "string" ? m.period_end : "";
  const dca = m.dca && typeof m.dca === "object" ? (m.dca as Record<string, unknown>) : null;
  if (!symbol || !periodStart || !periodEnd) return null;
  return {
    strategy: strategyId,
    label: typeof m.label === "string" ? m.label : null,
    kind: typeof m.kind === "string" ? m.kind : null,
    symbol,
    periodStart,
    periodEnd,
    netProfitPct: toNumber(m.net_profit_pct) ?? 0,
    maxDrawdownPct: toNumber(m.max_drawdown_pct) ?? 0,
    profitFactor: toNumber(m.profit_factor),
    winRatePct: toNumber(m.win_rate_pct),
    totalTrades: toNumber(m.total_trades) ?? 0,
    vsLumpPct: toNumber(dca?.vs_lump_pct) ?? toNumber(m.vs_lump_pct),
    allocatedPct: toNumber(dca?.allocated_pct) ?? toNumber(m.allocated_pct),
  };
}

/** Tearsheet rows from `strategy_tearsheets`, in table order. Optional `slugs` pins membership. */
export function strategyReadsFromTable(
  rows: readonly unknown[],
  slugs?: readonly string[],
): StrategyRead[] {
  const reads: StrategyRead[] = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const r = row as { strategy_id?: unknown; metrics?: unknown };
    if (typeof r.strategy_id !== "string") continue;
    const read = toStrategyRead(r.strategy_id, r.metrics);
    if (read) reads.push(read);
  }
  if (!slugs || slugs.length === 0) return reads;
  const bySlug = new Map(reads.map((read) => [read.strategy, read]));
  return slugs.map((slug) => bySlug.get(slug)).filter((r): r is StrategyRead => Boolean(r));
}

/**
 * Every published tearsheet, or the `slugs` subset when the caller pins membership.
 * dashboard-api first (`/v1/tables/strategy_tearsheets`), then Supabase. Empty when
 * neither read is available — never a fabricated card.
 */
export async function fetchStrategies(slugs?: readonly string[]): Promise<StrategyRead[]> {
  if (dashboardApiBase()) {
    const body = await getRaw(
      "/v1/tables/strategy_tearsheets?select=strategy_id,metrics&order=strategy_id.asc&limit=200",
    );
    return strategyReadsFromTable(rowsFromDashboardBody(body), slugs);
  }
  if (!supabase) return [];
  const query = supabase.from(STRATEGY_TABLE).select("strategy_id, metrics");
  const filtered =
    slugs && slugs.length > 0 ? query.in("strategy_id", [...slugs]) : query.limit(200);
  const { data, error } = await filtered;
  if (error || !data) return [];
  return strategyReadsFromTable(data, slugs);
}

/** A growth figure as an annual rate, from a total return over a dated period. */
export function cagrPct(totalReturnPct: number, startISO: string, endISO: string): number | null {
  const start = Date.parse(startISO);
  const end = Date.parse(endISO);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
  const years = (end - start) / (365.25 * 24 * 60 * 60 * 1000);
  if (years <= 0) return null;
  const growth = 1 + totalReturnPct / 100;
  if (growth <= 0) return null;
  return (Math.pow(growth, 1 / years) - 1) * 100;
}

/** The slug convention digiquant's own library uses to spot the DCA strategy. */
export function isDcaStrategy(slug: string): boolean {
  return /sdca|dca/.test(slug);
}
