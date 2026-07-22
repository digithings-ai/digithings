/**
 * Shapes emitted by `digiquant.tearsheet_data` (the unified TearsheetData schema).
 * The chart-facing shapes (TearsheetSeriesPoint, TearsheetTrade) are owned by the
 * finance-tearsheet family (#1463); the full payload schema and the Olympus
 * wrapper below stay app-local data wiring.
 */

import type {
  ContributionReturnPoint,
  TearsheetSeriesPoint,
  TearsheetTrade,
} from '@digithings/web';

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
  equity_curve: TearsheetSeriesPoint[];
  drawdown_curve: TearsheetSeriesPoint[];
  trades: TearsheetTrade[];
  notes: string[];
}

export interface PerformanceHoldingRow {
  ticker: string;
  category: string | null;
  weightPct: number | null;
  unrealizedReturnPct: number | null;
  realizedReturnPct: number | null;
  attributionDate: string | null;
}

export interface PortfolioReturnPoint {
  date: string;
  nav: number;
  /** Return rebased to 0% at the first stored NAV observation. */
  returnPct: number;
}

export type PerformanceReturnsSource = 'persisted' | 'derived' | 'mixed' | 'unavailable';

export interface OlympusTearsheet {
  currentNav: number | null;
  netReturnPct: number | null;
  benchmarkReturnPct: number | null;
  relativeReturnPct: number | null;
  benchmarkTicker: string;
  returnsSource: PerformanceReturnsSource;
  metricsAsOf: string | null;
  inceptionDate: string | null;
  holdingsAsOf: string | null;
  generatedAt: string | null;
  navSeries: PortfolioReturnPoint[];
  contributionSeries: ContributionReturnPoint[];
  currentHoldings: PerformanceHoldingRow[];
  historicalHoldings: PerformanceHoldingRow[];
}

/** Compact card summary in `strategies/index.json` (the library manifest). */
export interface StrategyIndexEntry {
  strategy: string;
  symbol: string;
  engine: string;
  period_start: string;
  period_end: string;
  net_profit_pct: number;
  max_drawdown_pct: number;
  profit_factor: number;
  win_rate_pct: number;
  total_trades: number;
  generated_at: string;
  href: string;
}
