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
 * Fail-closed contract for the published NAV series (#2599 / #3029) — must match
 * the dashboard's `lib/accounting-views.ts` view name, with no client fallback.
 */
export const ACCOUNTING_NAV_VIEW = "public_accounting_nav_history" as const;

/**
 * Read-only columns. Deliberately the curated public set: no positions, no
 * cash figures beyond the published percentages, nothing that is not already on
 * digiquant.io's public portfolio surface.
 */
const NAV_COLUMNS = "date, nav, cash_pct, invested_pct, day_return_pct, source";

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

/** The published NAV series, oldest first. Empty when unconfigured or missing. */
export async function fetchNav(): Promise<NavPoint[]> {
  if (!supabase) return [];
  const { data, error } = await supabase
    .from(ACCOUNTING_NAV_VIEW)
    .select(NAV_COLUMNS)
    .order("date", { ascending: true });
  if (error || !data) return [];
  return data
    .map((row) => {
      const r = row as { date?: unknown; nav?: unknown };
      const date = typeof r.date === "string" ? r.date : null;
      const nav = Number(r.nav);
      if (!date || !Number.isFinite(nav)) return null;
      return { date, nav };
    })
    .filter((p): p is NavPoint => p !== null);
}

/**
 * The benchmark leg, from the keyless R2 Worker (`GET /v1/market/closes`).
 *
 * `NEXT_PUBLIC_MARKET_DATA_URL` is the same var the price tape reads and is
 * required in prod; unset returns empty (there is deliberately no Supabase
 * fallback for prices).
 */
export async function fetchBenchmark(fromDate: string): Promise<PricePoint[]> {
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

/**
 * The library index, newest row per strategy, or `[]` when unavailable.
 *
 * `slugs` pins the membership (and therefore the card order) to the four the
 * band shows, so an unexpected row in the table can never appear on the landing
 * page.
 */
export async function fetchStrategies(slugs: readonly string[]): Promise<StrategyRead[]> {
  if (!supabase) return [];
  const { data, error } = await supabase
    .from(STRATEGY_TABLE)
    .select("strategy_id, metrics")
    .in("strategy_id", slugs as string[]);
  if (error || !data) return [];
  const bySlug = new Map<string, StrategyRead>();
  for (const row of data) {
    const r = row as { strategy_id?: unknown; metrics?: unknown };
    if (typeof r.strategy_id !== "string") continue;
    const read = toStrategyRead(r.strategy_id, r.metrics);
    if (read) bySlug.set(read.strategy, read);
  }
  return slugs.map((slug) => bySlug.get(slug)).filter((r): r is StrategyRead => Boolean(r));
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
