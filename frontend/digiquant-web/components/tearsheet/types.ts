/** Shapes emitted by `digiquant.tearsheet_data` (the unified TearsheetData schema). */

export interface TearsheetPoint {
  t: string;
  v: number;
}

/** One daily OHLC bar for the price candlestick chart (schema 1.1). */
export interface OHLCBar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
}

export interface TearsheetTrade {
  n: number;
  direction: "long" | "short";
  entry_label: string;
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  qty: number;
  pnl: number;
  pnl_pct: number;
  equity_after: number;
  exit_reason: string;
  max_runup_pct: number;
  max_drawdown_pct: number;
}

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
  equity_curve: TearsheetPoint[];
  drawdown_curve: TearsheetPoint[];
  /** Full-history OHLC (may span before ``trade_start``); absent on schema 1.0. */
  ohlc_bars?: OHLCBar[];
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
  net_profit_pct: number;
  max_drawdown_pct: number;
  profit_factor: number;
  win_rate_pct: number;
  avg_trade_pct: number;
  total_trades: number;
  generated_at: string;
  href: string;
}
