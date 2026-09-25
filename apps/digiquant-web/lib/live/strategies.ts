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
export function toIndexEntry(m: TearsheetData): StrategyIndexEntry {
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

/**
 * Local-only fallback for a slug not in the live store — e.g. a research
 * diagnostic tearsheet that is deliberately never pushed to Supabase (see
 * `digiquant/scripts/build_round8_diagnostic_tearsheet.py`). Reads the static
 * JSON some build step dropped at `public/strategies/<slug>.json`; production
 * ships no such files for published strategies, so this is a no-op there.
 */
async function fetchTearsheetFromStaticJson(slug: string): Promise<TearsheetData | null> {
  try {
    const res = await fetch(`/strategies/${slug}.json`);
    if (!res.ok) return null;
    return (await res.json()) as TearsheetData;
  } catch {
    return null;
  }
}

/** Full tearsheet payload for one strategy, or `null` if unavailable. */
export async function fetchTearsheet(slug: string): Promise<TearsheetData | null> {
  if (!supabase) return fetchTearsheetFromStaticJson(slug);
  const { data, error } = await supabase
    .from(TABLE)
    .select("metrics")
    .eq("strategy_id", slug)
    .maybeSingle();
  if (error || !data) return fetchTearsheetFromStaticJson(slug);
  return data.metrics as TearsheetData;
}

/** Library index (one card per strategy), or `[]` if unavailable. */
export async function fetchStrategyIndex(): Promise<StrategyIndexEntry[]> {
  if (!supabase) return [];
  const { data, error } = await supabase.from(TABLE).select("strategy_id, metrics");
  if (error || !data) return [];
  return data.map((row) => toIndexEntry(row.metrics as TearsheetData));
}
