/**
 * Domain types — assembled shapes returned by the data layer and consumed by
 * components. These are derived from Supabase table rows but are NOT raw rows;
 * they add computed fields and restructure data for frontend consumption.
 */

// ---------------------------------------------------------------------------
// Supabase raw row re-exports (aliased for internal use)
// ---------------------------------------------------------------------------
import type { TableRow } from './database.types';

export type SnapshotRow = TableRow<'daily_snapshots'>;
export type PositionRow = TableRow<'positions'>;
export type ThesisRow = TableRow<'theses'>;
export type DocumentRow = TableRow<'documents'>;
export type NavHistoryRow = TableRow<'nav_history'>;
export type PortfolioMetricsRow = TableRow<'portfolio_metrics'>;

// ---------------------------------------------------------------------------
// Assembled domain types (transformed by queries.ts)
// ---------------------------------------------------------------------------

/** A single holding as returned to components. */
export interface Position {
  ticker: string;
  name: string;
  type: 'LONG' | 'SHORT';
  weight_actual: number;
  /** Snapshot target weight from digest `proposed_positions` when present (for target vs actual). */
  weight_target?: number | null;
  /** Change vs previous positions date (percentage points). */
  weight_delta?: number | null;
  current_price: number | null;
  entry_price: number | null;
  entry_date: string | null;
  rationale: string;
  thesis_ids: string[];
  category: string;
  pm_notes: string;
  stats: Record<string, unknown>;
  /** Filled by refresh_performance_metrics.py after close (optional). */
  unrealized_pnl_pct?: number | null;
  day_change_pct?: number | null;
  since_entry_return_pct?: number | null;
  contribution_pct?: number | null;
  metrics_as_of?: string | null;
  /** Unsigned per-position conviction 1–3 (cyan pip meter). */
  conviction?: number | null;
  /** Advisory risk envelope (migration 039); null on ungraded rows. */
  stop_loss_pct?: number | null;
  target_pct_gain?: number | null;
  horizon_days?: number | null;
  /** Grouping bucket for the Holdings sector grouping. */
  sector_bucket?: string | null;
}

/** Active investment thesis as returned to components. */
export interface Thesis {
  id: string;
  name: string;
  vehicle: string | null;
  invalidation: string | null;
  status: string | null;
  notes: string | null;
  // Widened (F1) — the richest DB columns, previously dropped in the mapping.
  /** Conviction strength 0.0–1.0; drives the cyan ConvictionMeter on the thesis card. */
  confidence: number | null;
  horizon: string | null;
  /** 'market' | 'vehicle' — splits the two-tier Theses ledger. */
  thesis_kind: string | null;
  /** "What confirms this" — structured evidence rows. */
  validation_criteria: string[];
  /** "What breaks this" — structured evidence rows. */
  invalidation_criteria: string[];
  /** For vehicle theses: the market view they express (null until backend populates). */
  linked_market_thesis_id: string | null;
}

/** One ranked recommendation from the digest `actionable_summary`. */
export interface ActionableItem {
  label: string;
  priority: number | null;
  rationale: string | null;
}

/** One tail-risk row from the digest `risk_radar`. */
export interface RiskItem {
  label: string;
  trigger: string | null;
  horizonHours: number | null;
}

/** The current regime/strategy as assembled from the latest snapshot. */
export interface PortfolioStrategy {
  regime: string;
  regime_label: 'bullish' | 'bearish' | 'caution' | 'neutral' | string;
  summary: string;
  actionable: string[];
  risks: string[];
  actionableItems: ActionableItem[];
  riskItems: RiskItem[];
  theses: Thesis[];
  next_review: string;
}

/** A proposed change to the portfolio. */
export interface ProposedPosition {
  ticker: string;
  weight_pct: number;
  action: string;
}

/** A rebalancing instruction. */
export interface RebalanceAction {
  ticker: string;
  current_pct: number;
  recommended_pct: number;
  action: string;
  /** PM LLM rationale from pm-rebalance.actions, when available. */
  rationale?: string;
}

/** Current position as stored in portfolio_management. */
export interface CurrentPosition {
  ticker: string;
  name: string;
  category: string;
  weight_pct: number;
  thesis_ids: string[];
  entry_date: string | null;
  entry_price_usd: number | null;
  notes: string;
}

/** Benchmark data for a single ticker. */
export interface BenchmarkData {
  current: number | null;
  history: Array<{ date: string; price: number }>;
}

/** Map of benchmark ticker → BenchmarkData. */
export type BenchmarkHistoryMap = Record<string, BenchmarkData>;

/** A single NAV data point for charts (aligned with nav_history). */
export interface NavChartPoint {
  date: string;
  nav: number;
  cash_pct?: number | null;
  invested_pct?: number | null;
}

/** One historical position row for sleeve / time-series aggregation. */
export interface PositionHistoryRow {
  date: string;
  ticker: string;
  weight_pct: number;
  category: string | null;
  thesis_id: string | null;
}

/** Execution / change ledger row (position_events). */
export interface DashboardPositionEvent {
  date: string;
  ticker: string;
  event: 'OPEN' | 'EXIT' | 'TRIM' | 'ADD' | 'HOLD';
  weight_pct: number | null;
  prev_weight_pct: number | null;
  weight_change_pct: number | null;
  price: number | null;
  thesis_id: string | null;
  reason: string | null;
}

/** On-demand price + events for an expanded position row chart. */
export interface PositionPriceChartEvent {
  date: string;
  event: 'OPEN' | 'EXIT' | 'TRIM' | 'ADD' | 'HOLD';
  price: number | null;
  reason: string | null;
  weight_pct: number | null;
  prev_weight_pct: number | null;
  weight_change_pct: number | null;
}

export interface PositionPriceChartData {
  priceHistory: Array<{ date: string; close: number; is_trading_day: boolean }>;
  events: PositionPriceChartEvent[];
}

/** Latest row from portfolio_metrics (server-computed; optional). */
export interface ServerPortfolioMetrics {
  date: string | null;
  as_of_date: string | null;
  pnl_pct: number | null;
  sharpe: number | null;
  volatility: number | null;
  max_drawdown: number | null;
  alpha: number | null;
  /** Derived from invested_pct (the portfolio_metrics.cash_pct column was dropped, #714). */
  cash_pct: number | null;
  invested_pct: number | null;
  generated_at: string | null;
}

/**
 * A single Atlas run's health + optional economics. The public dashboard reads
 * from the anon-safe `atlas_run_health` view (status, segment counts, timing);
 * spend telemetry fields are null unless a BFF with service-role access is wired.
 */
export interface AtlasRunDiagnostics {
  run_id: string;
  run_type: string | null;
  run_date: string | null;
  model: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_s: number | null;
  llm_calls: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cached_tokens: number | null;
  search_calls: number | null;
  grounding_ok: number | null;
  grounding_failed: number | null;
  est_cost_usd: number | null;
  segments_total: number | null;
  segments_ok: number | null;
  segments_carried: number | null;
  segments_failed: number | null;
  error_summary: string | null;
  /** Phase health `{phaseN_outputs: {ok, failed, carried}}` + `by_kind` cost split. */
  breakdown: Record<string, unknown> | null;
  created_at: string | null;
}

/** Chart row for the Performance page NAV chart — portfolio + optional benchmark columns. */
export interface PerfChartPoint {
  date: string;
  portfolio: number | null;
  [benchmark: string]: number | null | string;
}

/** One observation for macro sparklines. */
export interface MacroSeriesPoint {
  obs_date: string;
  value: number | null;
}

/** One row in thesis_id history (theses table over time). */
export interface ThesisHistoryPoint {
  date: string;
  thesis_id: string;
  name: string;
  status: string | null;
  notes: string | null;
}

/** Portfolio meta / identity fields. */
export interface PortfolioMeta {
  name: string;
  base_currency: string;
  /** Run *date* (YYYY-MM-DD) of the latest daily_snapshots row driving this dashboard. */
  last_updated: string | null;
  /** Wall-clock UTC timestamp (daily_snapshots.created_at) of that run — for true-age freshness. */
  last_run_at: string | null;
  benchmarks: string[];
  inception_date?: string;
  /** Run type for the latest daily_snapshots row driving this dashboard. */
  latest_snapshot_run_type?: 'baseline' | 'delta' | null;
}

/** Top-level portfolio object. */
export interface Portfolio {
  meta: PortfolioMeta;
  snapshots: NavChartPoint[];
  strategy: PortfolioStrategy;
}

/** Portfolio management block. */
export interface PortfolioManagement {
  current_positions: CurrentPosition[];
  proposed_positions: ProposedPosition[];
  constraints: Record<string, unknown>;
  rebalance_actions: RebalanceAction[];
  pnl_fx_impact: number | null;
}

/** Computed summary metrics for the performance page. */
export interface CalculatedMetrics {
  /** Derived from portfolio_metrics.pnl_pct; null when the metrics row is absent. */
  portfolio_pnl: number | null;
  /** Sum of effective position weights (always has a real fallback — never null). */
  total_invested: number;
  /** 100 − total_invested (always has a real fallback — never null). */
  cash_pct: number;
  /** null when portfolio_metrics row is absent (prefer "—" over fake zero in UI). */
  sharpe: number | null;
  volatility: number | null;
  max_drawdown: number | null;
  alpha: number | null;
}

/** Parsed delta-request.json envelope for library badges and diff scoping. */
export interface DeltaRequestMeta {
  changed_paths: string[];
  baseline_date: string | null;
  op_paths: string[];
}

/** Parsed research_changelog payload (per-document delta summary for a date). */
export interface ResearchChangelogItem {
  target_document_key: string;
  status: string;
  one_line_change?: string;
  severity?: string;
}

export interface ResearchChangelogMeta {
  items: ResearchChangelogItem[];
  baseline_date: string | null;
}

/** A document record as returned to the Research Library. */
export interface Doc {
  id: string;
  date: string;
  title: string;
  type: string | null;
  phase: number | null;
  category: string | null;
  segment: string | null;
  sector: string | null;
  runType: string | null;
  path: string;
  // Enriched fields added by the Library page
  filename?: string;
  cadence?: string;
  content?: string;
}

/** One per-ticker pipeline document bundled for dashboard observability. */
export interface PipelineTickerDoc {
  document_key: string;
  ticker: string;
  payload: Record<string, unknown>;
}

/** Track B / PM pipeline JSON loaded for the dashboard as-of date (markdown derived in UI). */
export interface PipelineObservabilityBundle {
  snapshot_date: string;
  market_thesis_exploration: Record<string, unknown> | null;
  thesis_vehicle_map: Record<string, unknown> | null;
  pm_allocation_memo: Record<string, unknown> | null;
  deliberation_session_index: Record<string, unknown> | null;
  /**
   * Per-ticker bull/bear `DebateSummary` docs. Carries both the Hermes pipeline
   * shape (`deliberation/{ticker}`, has `net_stance`) and any operator-flow
   * `deliberation-transcript/{date}/{ticker}` docs; consumers filter by shape.
   */
  deliberation_transcripts: PipelineTickerDoc[];
  asset_recommendations: PipelineTickerDoc[];
  /** Hermes `risk-debate` doc (aggressive/conservative/key_tension), or null. */
  risk_debate: Record<string, unknown> | null;
  /** Hermes `pm-rebalance` decision doc (actions carry per-ticker rationale), or null. */
  pm_rebalance: Record<string, unknown> | null;
}

/** The complete data object returned by getFullDashboardData(). */
export interface DashboardData {
  portfolio: Portfolio;
  positions: Position[];
  portfolio_management: PortfolioManagement;
  /** Position weights over time (includes category / thesis for sleeve charts). */
  position_history: PositionHistoryRow[];
  /** Recent execution events (OPEN / EXIT / TRIM / ADD / HOLD). */
  position_events: DashboardPositionEvent[];
  ratios: Array<{ long_ticker: string; short_ticker: string; net_weight: number }>;
  docs: Doc[];
  /** Server-side metrics snapshot (when portfolio_metrics row exists). */
  server_portfolio_metrics: ServerPortfolioMetrics | null;
  /** Per trading day: paths touched by delta-request.json (when published). */
  delta_request_meta_by_date: Record<string, DeltaRequestMeta>;
  /** Per trading day: research_changelog.json items (after fold_document_deltas). */
  research_changelog_by_date: Record<string, ResearchChangelogMeta>;
  /** Fallback for calendar baseline vs delta when document rows omit `run_type`. */
  snapshot_run_type_by_date: Record<string, 'baseline' | 'delta'>;
  benchmarks: BenchmarkHistoryMap;
  /** Distinct tickers in price_history (view); sorted with majors first. */
  price_history_tickers: string[];
  calculated: CalculatedMetrics;
  /** Short context bullets derived from the snapshot JSONB digest. */
  snapshot_context_bullets: string[];
  /** Recent points per series_id for macro preview (curated list). */
  macro_series_preview: Record<string, MacroSeriesPoint[]>;
  /** Published thesis / PM pipeline artifacts for `portfolio.meta.last_updated` when present. */
  pipeline_observability: PipelineObservabilityBundle | null;
}

// ---------------------------------------------------------------------------
// Advanced Statistics (performance page)
// ---------------------------------------------------------------------------

export interface PerformanceMetrics {
  tradingDays: number;
  totalReturn: number;
  annReturn: number;
  annVol: number;
  sharpe: number;
  sortino: number;
  maxDd: number;
  ddStart: string;
  ddEnd: string;
  currDd: number;
  winRate: number;
  upDays: number;
  downDays: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  calmar: number;
  bestDay: number;
  worstDay: number;
  beta: number | null;
  correlation: number | null;
  alphaAnn: number | null;
  trackingError: number | null;
  infoRatio: number | null;
}
