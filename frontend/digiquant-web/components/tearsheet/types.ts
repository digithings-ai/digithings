/** Shapes emitted by `digiquant.tearsheet_data` (the unified TearsheetData schema).
 *  The chart-facing subset — series point, OHLC bar (schema 1.1), trade — is
 *  the finance-tearsheet family's (#1463), re-exported so app data wiring and
 *  the shared render surfaces speak one set of names. */

import type {
  TearsheetOhlcBar,
  TearsheetSeriesPoint,
  TearsheetTrade,
} from "@digithings/web";

export type { TearsheetOhlcBar, TearsheetSeriesPoint, TearsheetTrade };

export interface TearsheetBreakdown {
  trades: number;
  net_profit: number;
  net_profit_pct: number;
  gross_profit: number;
  gross_loss: number;
  percent_profitable: number;
  profit_factor: number;
  avg_trade: number;
  wins: number;
  losses: number;
}

/** Schema 1.3 DCA block. Every `*_pct` field is a ×100 true percent (#2552). */
export interface TearsheetDcaBreakdown {
  vs_lump_pct: number;
  vs_flat_dca_pct: number;
  avg_cost_basis: number | null;
  final_cost_basis_vs_price: number | null;
  capital_deployed_pct: number;
  capital_deployed_peak_pct: number;
  units_accumulated: number;
  buy_days: number;
  sell_days: number;
  no_trade_days: number;
  avg_risk: number | null;
  avg_rate: number | null;
  /** Final MTM allocated %; never capital_deployed (goes negative after sells). */
  allocated_pct?: number | null;
  /** Days with a non-zero buy fill — not curve-sign `buy_days`. */
  fill_buy_days?: number | null;
  /** Days with a non-zero sell fill — not curve-sign `sell_days`. */
  fill_sell_days?: number | null;
}

/** Valuation rails overlay (low / median / high) from the #3168 diagnostics. */
export interface TearsheetRailPoint {
  t: string;
  low: number;
  median: number;
  high: number;
}

export interface TearsheetFillMarker {
  t: string;
  side: "buy" | "sell";
  book_frac: number;
  price: number;
  trade_usd: number;
}

export interface TearsheetIndicatorCurve {
  name: string;
  display_name: string;
  weight: number;
  in_index: boolean;
  points: TearsheetSeriesPoint[];
}

export interface TearsheetData {
  schema_version: string;
  strategy: string;
  symbol: string;
  engine: string;
  generated_at: string;
  data_source: string;
  period_start: string;
  period_end: string;
  /** Days the live signal trails the backtest (schema 1.2+); absent / 0 = none. */
  signal_delay_days?: number;
  bars: number;
  initial_capital: number;
  final_equity: number;
  net_profit: number;
  net_profit_pct: number;
  max_drawdown_pct: number;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  calmar_ratio: number | null;
  /** Null (not 0) on DCA books — trade-based KPIs do not apply (#3171). */
  profit_factor: number | null;
  win_rate_pct: number | null;
  total_trades: number;
  avg_trade: number;
  overall: TearsheetBreakdown;
  long: TearsheetBreakdown | null;
  short: TearsheetBreakdown | null;
  equity_curve: TearsheetSeriesPoint[];
  drawdown_curve: TearsheetSeriesPoint[];
  /** Full-history OHLC (may span before ``trade_start``); absent on schema 1.0. */
  ohlc_bars?: TearsheetOhlcBar[];
  trades: TearsheetTrade[];
  notes: string[];
  /** Present when the payload comes from Supabase `strategy_tearsheets.metrics`
   *  (#1069): index extras that live in settings, not the backtest, plus the
   *  derived current signal. Absent on legacy static-JSON payloads. */
  label?: string;
  kind?: string;
  avg_trade_pct?: number | null;
  current_signal?: CurrentSignal;
  /** Schema 1.3 — absent on every Slapper payload. */
  dca?: TearsheetDcaBreakdown | null;
  /** Optional diagnostic series; degrade when absent (publish may lag). */
  rails?: TearsheetRailPoint[];
  risk_curve?: TearsheetSeriesPoint[];
  cost_basis_curve?: TearsheetSeriesPoint[];
  capital_deployed_curve?: TearsheetSeriesPoint[];
  lump_equity_curve?: TearsheetSeriesPoint[];
  flat_dca_equity_curve?: TearsheetSeriesPoint[];
  /** Mark-to-market % of book in the asset. Not capital_deployed (goes negative after sells). */
  allocated_pct_curve?: TearsheetSeriesPoint[];
  fill_markers?: TearsheetFillMarker[];
  indicator_curves?: TearsheetIndicatorCurve[];
  indicator_weights?: Record<string, number>;
  curve_knees?: { buy_knee_risk: number; sell_knee_risk: number; preset: string };
  /** Walk-forward OOS vs flat DCA. False / omitted = do not claim an OOS win. */
  beats_flat_dca_oos?: boolean | null;
  /** Index extras duplicated onto the Supabase metrics row (#1069). */
  vs_lump_pct?: number | null;
  vs_flat_dca_pct?: number | null;
  capital_deployed_pct?: number | null;
  allocated_pct?: number | null;
}

export interface CurrentSignal {
  /** "long" | "short" | "flat" on slappers; DCA books may still send long/flat. */
  position: string;
  entry_label: string;
  last_signal_date: string;
  last_price: number | null;
  /** Composite risk 0–100 (DCA). */
  risk?: number | null;
  /** Band label; renderer derives from `risk` when omitted. */
  band?: string | null;
  /** Today's rate as a ×100 percent (cash for buys, units for sells). */
  daily_rate_pct?: number | null;
}

/** Compact card summary in `strategies/index.json` (the library manifest). */
export interface StrategyIndexEntry {
  strategy: string;
  /** Human label, e.g. "BTC long/short" (present in index.json). */
  label?: string;
  /** Taxonomy slug for library filters — `long_short`, `long_only`, etc. */
  kind?: string;
  symbol: string;
  engine: string;
  period_start: string;
  period_end: string;
  /** Days the live signal trails the backtest (index.json, schema 1.2+); absent / 0 = none. */
  signal_delay_days?: number;
  net_profit_pct: number;
  max_drawdown_pct: number;
  profit_factor: number | null;
  win_rate_pct: number | null;
  avg_trade_pct: number | null;
  total_trades: number;
  generated_at: string;
  href: string;
  vs_lump_pct?: number | null;
  vs_flat_dca_pct?: number | null;
  capital_deployed_pct?: number | null;
  allocated_pct?: number | null;
  beats_flat_dca_oos?: boolean | null;
}
