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
 * Reuses the shared browser client (`supabaseClient.ts`), which is `null` when the
 * public env vars are unset — callers degrade to a loading/empty state, and the
 * static export still builds.
 */
import { type StrategyIndexEntry, type TearsheetData } from "@/components/tearsheet/types";
import { supabase } from "./supabaseClient";

const TABLE = "strategy_tearsheets";

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
    avg_trade_pct: m.avg_trade_pct ?? 0,
    total_trades: m.total_trades,
    generated_at: m.generated_at,
    href: `/strategies/${m.strategy}`,
  };
}

/** Full tearsheet payload for one strategy, or `null` if unavailable. */
export async function fetchTearsheet(slug: string): Promise<TearsheetData | null> {
  if (!supabase) return null;
  const { data, error } = await supabase
    .from(TABLE)
    .select("metrics")
    .eq("strategy_id", slug)
    .maybeSingle();
  if (error || !data) return null;
  return data.metrics as TearsheetData;
}

/** Library index (one card per strategy), or `[]` if unavailable. */
export async function fetchStrategyIndex(): Promise<StrategyIndexEntry[]> {
  if (!supabase) return [];
  const { data, error } = await supabase.from(TABLE).select("strategy_id, metrics");
  if (error || !data) return [];
  return data.map((row) => toIndexEntry(row.metrics as TearsheetData));
}
