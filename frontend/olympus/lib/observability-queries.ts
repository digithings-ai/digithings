/**
 * Observability dashboard data access (Pillar 3D).
 *
 * Reads the decision track record (`decision_log`) the Decision Scorecard needs, plus
 * — via `fetchAtlasRunDiagnostics` — run health from the anon-readable
 * `atlas_run_health` view (migration 041). Kept separate from `getFullDashboardData`
 * so the main Morning Read bundle stays lean; these fire only when their consumer mounts.
 *
 * Attribution and per-position risk now live on Performance/Holdings (which read their own
 * sources). System reads run telemetry from `atlas_run_health` — the curated projection
 * that bypasses the base-table RLS on `atlas_run_diagnostics` (migration 033). Spend
 * telemetry (cost, tokens, error_summary, breakdown) is intentionally excluded from the
 * view; economics tiles render "—" on the public anon-key dashboard.
 *
 * Every query is FAIL-SOFT: a missing/forbidden source (e.g. an empty book) resolves to an
 * empty result rather than throwing, so consumers render a clean empty state instead of an
 * error wall.
 */

import { supabase, isSupabaseConfigured } from './supabase';
import type { TableRow, ViewRow } from './database.types';
import type { AtlasRunDiagnostics } from './types';
import { computeEffectivePortfolioRiskMetrics } from './portfolio-risk-metrics';
import { backtestDecisions, type DecisionInput } from './decision-track-record';
import type { TearsheetSeriesPoint } from '@digithings/web';
import type {
  DecisionLogRow,
  OlympusTearsheet,
  TearsheetBreakdown,
  TearsheetData,
} from '@/components/tearsheet/types';

const DECISION_LIMIT = 1000;
const TEARSHEET_NAV_LIMIT = 2000;
const ATTRIBUTION_LIMIT = 500;

export interface ObservabilityData {
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

export async function fetchObservabilityData(): Promise<ObservabilityData> {
  // Distinguish a total misconfiguration (no Supabase env) from a configured-but-empty book:
  // throw so the page shows a clear error, matching the main data layer (lib/queries.ts).
  if (!isSupabaseConfigured() || !supabase) {
    throw new Error(
      'Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY). ' +
        'Observability data cannot be loaded.'
    );
  }
  const decisionsRes = await safeSelect<TableRow<'decision_log'>>('decision_log', (sb) =>
    sb
      .from('decision_log')
      .select(
        'id,run_id,run_date,ticker,stance,conviction,thesis,benchmark,holding_days,status,actual_return,alpha,reflection,resolved_at,created_at'
      )
      .order('run_date', { ascending: false })
      .limit(DECISION_LIMIT)
  );
  return { decisions: decisionsRes.rows };
}

const RUN_DIAGNOSTICS_LIMIT = 30;

/**
 * Read run health from the anon-readable `atlas_run_health` view (migration 041).
 * Cost/tokens/grounding fields are null on the public dashboard — the view
 * deliberately omits operator-internal spend telemetry. Fail-soft: empty array
 * on missing source / RLS deny.
 */
export async function fetchAtlasRunDiagnostics(): Promise<AtlasRunDiagnostics[]> {
  const res = await safeSelect<ViewRow<'atlas_run_health'>>('atlas_run_health', (sb) =>
    sb
      .from('atlas_run_health')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(RUN_DIAGNOSTICS_LIMIT)
  );
  return res.rows.map((r) => ({
    run_id: r.run_id,
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
   Assembles the hybrid OlympusTearsheet: a live-NAV track (TearsheetData,
   engine='live') + the decision track-record (TS port of atlas/backtest.py) +
   absorbed per-position attribution. The builder is pure and unit-tested; the
   fetch wrapper is fail-soft (empty/RLS-deny → a zeroed empty-state build). */

/** Keep only the rows whose date equals the most recent date present. */
function latestDateRows<T extends { date: string | null }>(rows: T[]): { rows: T[]; date: string | null } {
  const date = rows.reduce<string | null>(
    (m, r) => (r.date && (m === null || r.date > m) ? r.date : m),
    null
  );
  return { rows: date === null ? [] : rows.filter((r) => r.date === date), date };
}

/** Drawdown (%) from a peak-to-current equity curve — mirrors tearsheet_data._drawdown_from_equity. */
function drawdownFromEquity(points: TearsheetSeriesPoint[]): TearsheetSeriesPoint[] {
  if (!points.length) return [];
  let peak = points[0].v;
  return points.map((p) => {
    peak = Math.max(peak, p.v);
    const dd = peak > 0 ? ((p.v - peak) / peak) * 100 : 0;
    return { t: p.t, v: dd };
  });
}

function emptyBreakdown(): TearsheetBreakdown {
  return {
    trades: 0,
    net_profit: 0,
    net_profit_pct: 0,
    gross_profit: 0,
    gross_loss: 0,
    percent_profitable: 0,
    profit_factor: 0,
    avg_trade: 0,
    wins: 0,
    losses: 0,
  };
}

export function buildOlympusTearsheet(args: {
  nav: TableRow<'nav_history'>[];
  decisions: TableRow<'decision_log'>[];
  metrics: TableRow<'portfolio_metrics'> | null;
  attribution: TableRow<'position_attribution'>[];
  now?: Date;
}): OlympusTearsheet {
  const navAsc = [...args.nav].sort((a, b) => a.date.localeCompare(b.date));
  const navPoints = navAsc.length;
  const equity: TearsheetSeriesPoint[] = navAsc.map((r) => ({ t: r.date, v: r.nav }));
  const snaps = navAsc.map((r) => ({ date: r.date, nav: r.nav }));
  const drawdown = navPoints >= 2 ? drawdownFromEquity(equity) : [];
  const risk = computeEffectivePortfolioRiskMetrics(
    args.metrics
      ? {
          sharpe: args.metrics.sharpe,
          volatility: args.metrics.volatility,
          max_drawdown: args.metrics.max_drawdown,
        }
      : null,
    snaps
  );
  const inceptionDate = navAsc[0]?.date ?? null;
  const latestNav = navAsc.length ? navAsc[navAsc.length - 1].nav : null;
  const initial = navAsc[0]?.nav ?? 100;
  const final = latestNav ?? initial;

  const live: TearsheetData = {
    schema_version: '1.0',
    strategy: 'Olympus',
    symbol: 'AI-INTELLIGENCE',
    engine: 'live',
    generated_at: (args.now ?? new Date()).toISOString(),
    data_source: 'nav_history',
    period_start: inceptionDate ?? '',
    period_end: navAsc[navAsc.length - 1]?.date ?? '',
    bars: navPoints,
    initial_capital: initial,
    final_equity: final,
    net_profit: final - initial,
    net_profit_pct: initial > 0 ? (final / initial - 1) * 100 : 0,
    max_drawdown_pct: risk.maxDrawdownPct ?? 0,
    sharpe_ratio: risk.sharpe,
    sortino_ratio: null,
    calmar_ratio: null,
    profit_factor: 0,
    win_rate_pct: 0,
    total_trades: 0, // live track is NAV-level; trade-level fields stay empty (template renders empty-states)
    avg_trade: 0,
    overall: emptyBreakdown(),
    long: emptyBreakdown(),
    short: emptyBreakdown(),
    equity_curve: equity,
    drawdown_curve: drawdown,
    trades: [],
    notes: [],
  };

  const resolved = args.decisions.filter(
    (d) => d.status === 'resolved' && d.alpha != null && d.actual_return != null
  );
  const inputs: DecisionInput[] = resolved.map((d) => ({
    run_date: d.run_date,
    return_frac: d.actual_return as number,
    benchmark_frac: (d.actual_return as number) - (d.alpha as number), // alpha = return − benchmark
    conviction: d.conviction,
    holding_days: d.holding_days,
  }));
  const decision = backtestDecisions(inputs);
  const decisionRows: DecisionLogRow[] = args.decisions.map((d) => ({
    run_date: d.run_date,
    ticker: d.ticker,
    stance: d.stance,
    conviction: d.conviction,
    status: d.status,
    alpha: d.alpha,
    holding_days: d.holding_days,
  }));

  return {
    live,
    navPoints,
    decision,
    decisionRows,
    nResolved: resolved.length,
    nPending: args.decisions.filter((d) => d.status === 'pending').length,
    attribution: args.attribution,
    attributionDate: latestDateRows(args.attribution).date,
    inceptionDate,
    latestNav,
    generatedAt: live.generated_at,
  };
}

export async function fetchOlympusTearsheet(): Promise<OlympusTearsheet> {
  if (!isSupabaseConfigured() || !supabase) {
    // Configured-but-empty must still render the empty-state tear sheet — return a zeroed build.
    return buildOlympusTearsheet({ nav: [], decisions: [], metrics: null, attribution: [] });
  }
  const [navRes, decisionsRes, metricsRes, attributionRes] = await Promise.all([
    safeSelect<TableRow<'nav_history'>>('nav_history', (sb) =>
      sb.from('nav_history').select('*').order('date', { ascending: true }).limit(TEARSHEET_NAV_LIMIT)
    ),
    safeSelect<TableRow<'decision_log'>>('decision_log', (sb) =>
      sb
        .from('decision_log')
        .select(
          'id,run_id,run_date,ticker,stance,conviction,thesis,benchmark,holding_days,status,actual_return,alpha,reflection,resolved_at,created_at'
        )
        .order('run_date', { ascending: false })
        .limit(DECISION_LIMIT)
    ),
    safeSelect<TableRow<'portfolio_metrics'>>('portfolio_metrics', (sb) =>
      sb.from('portfolio_metrics').select('*').order('date', { ascending: false }).limit(1)
    ),
    safeSelect<TableRow<'position_attribution'>>('position_attribution', (sb) =>
      sb
        .from('position_attribution')
        .select('*')
        .order('date', { ascending: false })
        .limit(ATTRIBUTION_LIMIT)
    ),
  ]);
  const attribution = latestDateRows(attributionRes.rows);
  return buildOlympusTearsheet({
    nav: navRes.rows,
    decisions: decisionsRes.rows,
    metrics: metricsRes.rows[0] ?? null,
    attribution: attribution.rows,
  });
}
