import { type TearsheetData, type TearsheetTrade } from "./types";

/** Calendar date shown in tables — exit when closed, else entry. */
export function tradeDate(t: TearsheetTrade): string {
  return t.exit_date || t.entry_date || "";
}

/** Open round-trip still marked to market (no realized P&L yet). */
export function isOpenTrade(t: TearsheetTrade): boolean {
  return !t.exit_date || t.exit_reason === "open";
}

/** The live leg at period end, if any. */
export function openTrade(trades: TearsheetTrade[], periodEnd?: string): TearsheetTrade | null {
  const explicit = trades.find(isOpenTrade);
  if (explicit) return explicit;
  if (!trades.length || !periodEnd) return null;
  const last = trades.reduce((a, b) => (a.n >= b.n ? a : b));
  if (last.exit_date === periodEnd) {
    return { ...last, exit_date: "", exit_reason: "open" };
  }
  return null;
}

/** Trades for UI — promotes a final-bar close to open when always-in-market. */
export function tradesForDisplay(data: Pick<TearsheetData, "trades" | "period_end">): TearsheetTrade[] {
  const live = openTrade(data.trades, data.period_end);
  if (!live || data.trades.find(isOpenTrade)) return data.trades;
  return data.trades.map((t) => (t.n === live.n ? live : t));
}

/** Latest mark for an open leg (generator sets exit_price to last close). */
export function markPriceForTrade(
  t: TearsheetTrade,
  data: Pick<TearsheetData, "ohlc_bars" | "period_end">,
): number {
  if (isOpenTrade(t) && t.exit_price > 0) return t.exit_price;
  const lastBar = data.ohlc_bars?.[data.ohlc_bars.length - 1];
  if (lastBar) return lastBar.c;
  return t.entry_price;
}

/** Unrealized % for an open leg; uses precomputed pnl_pct when present. */
export function unrealizedReturnPct(t: TearsheetTrade, mark: number): number {
  if (!isOpenTrade(t)) return t.pnl_pct;
  if (t.exit_reason === "open") return t.pnl_pct;
  const entry = t.entry_price;
  if (entry <= 0) return 0;
  if (t.direction === "long") return (mark / entry - 1) * 100;
  return ((entry - mark) / entry) * 100;
}

/** Closed trades only — unrealized open legs stay out of cumulative P&L charts. */
export function closedTrades(trades: TearsheetTrade[]): TearsheetTrade[] {
  return trades.filter((t) => !isOpenTrade(t));
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

/** Chronological per-trade % returns for the P&L bar chart (open leg last). */
export function tradesForPnlChart(
  data: Pick<TearsheetData, "trades" | "period_end" | "ohlc_bars">,
): TradeReturnBar[] {
  const display = tradesForDisplay(data);
  const rows: TradeReturnBar[] = closedTrades(display)
    .map((t) => ({
      t: t.exit_date || t.entry_date,
      pct: t.pnl_pct,
      open: false,
      trade: t,
    }))
    .sort((a, b) => new Date(a.t).getTime() - new Date(b.t).getTime());

  const live = openTrade(display, data.period_end);
  if (live) {
    const mark = markPriceForTrade(live, data);
    rows.push({
      t: data.period_end || live.entry_date,
      pct: unrealizedReturnPct(live, mark),
      open: true,
      trade: live,
    });
  }
  return rows;
}

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

/** Per-direction trade stats for the long/short breakdown table. */
export interface BreakdownTradeStats {
  avgWinPct: number | null;
  avgLossPct: number | null;
  bestPct: number | null;
  worstPct: number | null;
}

export function breakdownTradeStats(trades: TearsheetTrade[]): BreakdownTradeStats {
  const closed = closedTrades(trades);
  if (closed.length === 0) {
    return {
      avgWinPct: null,
      avgLossPct: null,
      bestPct: null,
      worstPct: null,
    };
  }
  const wins = closed.filter((t) => t.pnl > 0);
  const losses = closed.filter((t) => t.pnl <= 0);
  const pcts = closed.map((t) => t.pnl_pct);
  return {
    avgWinPct: wins.length ? mean(wins.map((t) => t.pnl_pct)) : null,
    avgLossPct: losses.length ? mean(losses.map((t) => t.pnl_pct)) : null,
    bestPct: Math.max(...pcts),
    worstPct: Math.min(...pcts),
  };
}

/** Open position first, then closed trades newest → oldest. */
export function sortTradesForLog(trades: TearsheetTrade[]): TearsheetTrade[] {
  return [...trades].sort((a, b) => {
    const aOpen = isOpenTrade(a);
    const bOpen = isOpenTrade(b);
    if (aOpen !== bOpen) return aOpen ? -1 : 1;
    return new Date(tradeDate(b)).getTime() - new Date(tradeDate(a)).getTime();
  });
}

/** Human-readable date cell for the trade log. */
export function tradeLogDate(t: TearsheetTrade): string {
  if (isOpenTrade(t)) return t.entry_date ? `${t.entry_date} → open` : "open";
  return tradeDate(t) || "—";
}
