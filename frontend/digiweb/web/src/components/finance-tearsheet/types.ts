/**
 * finance-tearsheet data shapes (#1463) — the chart-facing subset of the
 * unified TearsheetData schema, promoted from
 * frontend/digiquant-web/components/tearsheet/{types,trades}.ts. Only what
 * the family's render surfaces consume lives here; full tearsheet payload
 * types and their derivation pipelines (series clipping, pivot stats, trade
 * sorting) stay app-owned data wiring.
 */

/** One point of a dated series (equity, drawdown, cumulative P&L …). */
export interface TearsheetSeriesPoint {
  t: string;
  v: number;
}

/** One daily OHLC bar for the price candlestick chart. */
export interface TearsheetOhlcBar {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
}

/** One round-trip trade — drives markers, hover cards, and trade-log rows. */
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

/** Open round-trip still marked to market (no realized P&L yet). */
export function isOpenTrade(t: TearsheetTrade): boolean {
  return !t.exit_date || t.exit_reason === "open";
}

/** One bar on the per-trade return chart. */
export interface TradeReturnBar {
  /** X-axis date (exit for closed; period end for the open leg). */
  t: string;
  /** Realized or unrealized return (%). */
  pct: number;
  /** Unrealized open position — rendered highlighted at the end. */
  open: boolean;
  /** Source trade for hover tooltips. */
  trade: TearsheetTrade;
}
