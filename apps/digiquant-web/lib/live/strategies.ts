/**
 * Live strategy reads for digiquant.io (#1069).
 *
 * The nightly pipeline (`digiquant/scripts/generate_tearsheets.py --push-supabase`)
 * upserts the FULL tearsheet payload into `strategy_tearsheets.metrics` — the same
 * shape the renderer used to fetch from `public/strategies/<slug>.json`, plus a
 * derived `current_signal` and the index extras (`label`/`kind`/`avg_trade_pct`).
 * So one anon-readable table backs both the library index and every tearsheet;
 * updating a row updates the site with no redeploy.
 *
 * Reads go through the official API table route. That table is not on the
 * worker allowlist today, so a 404 withholds every statistic. There is no
 * Supabase fallback and no invented performance.
 */
import { type StrategyIndexEntry, type TearsheetData } from "@/components/tearsheet/types";
import { officialGet, STRATEGY_ROUTE } from "@/lib/official-api";

/** Project the index-card fields out of a full tearsheet payload. */
function toIndexEntry(m: TearsheetData): StrategyIndexEntry {
  return {
    strategy: m.strategy,
    label: m.label,
    kind: m.kind,
    symbol: m.symbol,
    engine: m.engine,
    period_start: m.period_start,
    period_end: m.period_end,
    signal_delay_days: m.signal_delay_days,
    net_profit_pct: m.net_profit_pct,
    max_drawdown_pct: m.max_drawdown_pct,
    profit_factor: m.profit_factor,
    win_rate_pct: m.win_rate_pct,
    avg_trade_pct: m.avg_trade_pct ?? null,
    total_trades: m.total_trades,
    generated_at: m.generated_at,
    href: `/strategies/${m.strategy}`,
    vs_lump_pct: m.dca?.vs_lump_pct ?? m.vs_lump_pct ?? null,
    vs_flat_dca_pct: m.dca?.vs_flat_dca_pct ?? m.vs_flat_dca_pct ?? null,
    capital_deployed_pct: m.dca?.capital_deployed_pct ?? m.capital_deployed_pct ?? null,
    allocated_pct: m.dca?.allocated_pct ?? m.allocated_pct ?? null,
    beats_flat_dca_oos: m.beats_flat_dca_oos ?? false,
  };
}

function metricsOf(row: unknown): TearsheetData | null {
  if (typeof row !== "object" || row === null) return null;
  const rec = row as { metrics?: unknown };
  if (typeof rec.metrics !== "object" || rec.metrics === null) return null;
  return rec.metrics as TearsheetData;
}

/** Full tearsheet payload for one strategy, or `null` if the API did not publish it. */
export async function fetchTearsheet(slug: string): Promise<TearsheetData | null> {
  const read = await officialGet(STRATEGY_ROUTE, {
    select: "strategy_id,metrics",
    "eq.strategy_id": slug,
    limit: "1",
  });
  if (!read.ok || !Array.isArray(read.body)) return null;
  return metricsOf(read.body[0]) ;
}

/** Library index (one card per strategy), or `[]` when the API withholds the table. */
export async function fetchStrategyIndex(): Promise<StrategyIndexEntry[]> {
  const read = await officialGet(STRATEGY_ROUTE, { select: "strategy_id,metrics", limit: "100" });
  if (!read.ok || !Array.isArray(read.body)) return [];
  return read.body.map(metricsOf).filter((m): m is TearsheetData => m !== null).map(toIndexEntry);
}
