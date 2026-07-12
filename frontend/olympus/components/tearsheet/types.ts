/**
 * Shapes emitted by `digiquant.tearsheet_data` (the unified TearsheetData schema).
 * The chart-facing shapes (TearsheetSeriesPoint, TearsheetTrade) are owned by the
 * finance-tearsheet family (#1463); the full payload schema and the Olympus
 * wrapper below stay app-local data wiring.
 */

import type { TearsheetSeriesPoint, TearsheetTrade } from '@digithings/web';
import type { DecisionTrackRecord } from '@/lib/decision-track-record';
import type { TableRow } from '@/lib/database.types';

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

/**
 * Olympus-specific wrapper around the ported TearsheetData. The live-NAV track reuses
 * TearsheetData (engine='live', strategy='Olympus', symbol='AI-INTELLIGENCE'); the
 * decision track-record track uses DecisionTrackRecord (TS port of atlas/backtest.py).
 * Each track degrades independently against its own empty-state predicate.
 */
export interface DecisionLogRow {
  run_date: string;
  ticker: string;
  stance: string;
  conviction: number | null;
  status: string;
  alpha: number | null;
  holding_days: number | null;
}

export interface OlympusTearsheet {
  live: TearsheetData; // engine='live', strategy='Olympus', symbol='AI-INTELLIGENCE'
  navPoints: number; // nav_history row count (gates the live track)
  decision: DecisionTrackRecord; // from lib/decision-track-record (resolved decisions only)
  decisionRows: DecisionLogRow[]; // resolved + pending, for the small decision-log table
  nResolved: number;
  nPending: number;
  attribution: TableRow<'position_attribution'>[]; // latest date (absorbed from System)
  attributionDate: string | null;
  inceptionDate: string | null; // first nav_history.date
  latestNav: number | null;
  generatedAt: string; // ISO now
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
