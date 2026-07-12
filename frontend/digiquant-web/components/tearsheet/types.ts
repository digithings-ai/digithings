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
  profit_factor: number;
  win_rate_pct: number;
  total_trades: number;
  avg_trade: number;
  overall: TearsheetBreakdown;
  long: TearsheetBreakdown;
  short: TearsheetBreakdown;
  equity_curve: TearsheetSeriesPoint[];
  drawdown_curve: TearsheetSeriesPoint[];
  /** Full-history OHLC (may span before ``trade_start``); absent on schema 1.0. */
  ohlc_bars?: TearsheetOhlcBar[];
  trades: TearsheetTrade[];
  notes: string[];
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
  profit_factor: number;
  win_rate_pct: number;
  avg_trade_pct: number;
  total_trades: number;
  generated_at: string;
  href: string;
}
