/**
 * Build column slices and per-slice metrics for the pivot statistics table.
 * Supports pivoting by trade direction, calendar year, or calendar quarter while
 * keeping the same metric rows across every column.
 */

import { clipPoints } from "./series";
import {
  avgTradePct,
  cagrPct,
  cagrPctFromGrowth,
  deriveRiskMetrics,
  recoveryFactor,
} from "./stats";
import { breakdownTradeStats, closedTrades } from "./trades";
import type { TearsheetBreakdown, TearsheetData, TearsheetSeriesPoint, TearsheetTrade } from "./types";

export type StatsPivot = "direction" | "year";

export interface StatSlice {
  id: string;
  label: string;
  startISO: string;
  endISO: string;
  trades: TearsheetTrade[];
  equity: TearsheetSeriesPoint[];
  drawdown: TearsheetSeriesPoint[];
  /** Precomputed breakdown from tearsheet JSON (direction pivot). */
  breakdown?: TearsheetBreakdown;
  /** When true, alpha vs buy-and-hold is meaningful for this slice. */
  allowAlpha: boolean;
}

export interface SliceMetrics {
  returnPct: number | null;
  cagrPct: number | null;
  maxDrawdownPct: number | null;
  sharpe: number | null;
  sortino: number | null;
  calmar: number | null;
  omega: number | null;
  volatilityPct: number | null;
  recovery: number | null;
  alphaPct: number | null;
  trades: number;
  wins: number;
  losses: number;
  winRatePct: number | null;
  profitFactor: number | null;
  avgTradePct: number | null;
  avgWinPct: number | null;
  avgLossPct: number | null;
  bestPct: number | null;
  worstPct: number | null;
}

function onOrBefore(iso: string, endISO: string): boolean {
  return new Date(iso).getTime() <= new Date(endISO).getTime();
}

function clipRange(points: TearsheetSeriesPoint[], startISO: string, endISO: string): TearsheetSeriesPoint[] {
  return points.filter((p) => onOrAfterDate(p.t, startISO) && onOrBefore(p.t, endISO));
}

function onOrAfterDate(iso: string, startISO: string): boolean {
  if (!startISO) return true;
  return new Date(iso).getTime() >= new Date(startISO).getTime();
}

function tradesInRange(trades: TearsheetTrade[], startISO: string, endISO: string): TearsheetTrade[] {
  const lo = new Date(startISO).getTime();
  const hi = new Date(endISO).getTime();
  return trades.filter((t) => {
    const exit = t.exit_date || t.entry_date;
    if (!exit) return false;
    const ts = new Date(exit).getTime();
    return ts >= lo && ts <= hi;
  });
}

function breakdownFromTrades(trades: TearsheetTrade[], returnPct: number | null): TearsheetBreakdown {
  const closed = closedTrades(trades);
  const wins = closed.filter((t) => t.pnl > 0);
  const losses = closed.filter((t) => t.pnl <= 0);
  const grossProfit = wins.reduce((s, t) => s + t.pnl, 0);
  const grossLoss = losses.reduce((s, t) => s + Math.abs(t.pnl), 0);
  const netProfit = closed.reduce((s, t) => s + t.pnl, 0);
  const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : wins.length > 0 ? Infinity : 0;
  const pct = returnPct ?? 0;
  return {
    trades: closed.length,
    net_profit: netProfit,
    net_profit_pct: pct,
    gross_profit: grossProfit,
    gross_loss: grossLoss,
    percent_profitable: closed.length > 0 ? (wins.length / closed.length) * 100 : 0,
    profit_factor: Number.isFinite(profitFactor) ? profitFactor : 0,
    avg_trade: closed.length > 0 ? netProfit / closed.length : 0,
    wins: wins.length,
    losses: losses.length,
  };
}

function periodReturnPct(equity: TearsheetSeriesPoint[]): number | null {
  if (equity.length < 2) return null;
  const first = equity[0].v;
  const last = equity[equity.length - 1].v;
  return first > 0 ? (last / first - 1) * 100 : null;
}

function maxDrawdownInSlice(drawdown: TearsheetSeriesPoint[]): number | null {
  if (drawdown.length === 0) return null;
  return drawdown.reduce((min, p) => (p.v < min ? p.v : min), drawdown[0].v);
}

function fullPeriodSlice(data: TearsheetData, equity: TearsheetSeriesPoint[], drawdown: TearsheetSeriesPoint[]): StatSlice {
  return {
    id: "full",
    label: "Full period",
    startISO: data.period_start,
    endISO: data.period_end,
    trades: data.trades,
    equity,
    drawdown,
    breakdown: data.overall,
    allowAlpha: true,
  };
}

export function buildStatSlices(data: TearsheetData, pivot: StatsPivot): StatSlice[] {
  const equity = clipPoints(data.equity_curve, data.period_start);
  const drawdown = clipPoints(data.drawdown_curve, data.period_start);
  const full = fullPeriodSlice(data, equity, drawdown);

  if (pivot === "direction") {
    return [
      { ...full, id: "all", label: "all", breakdown: data.overall },
      {
        id: "long",
        label: "long",
        startISO: data.period_start,
        endISO: data.period_end,
        trades: data.trades.filter((t) => t.direction === "long"),
        equity,
        drawdown,
        breakdown: data.long,
        allowAlpha: false,
      },
      {
        id: "short",
        label: "short",
        startISO: data.period_start,
        endISO: data.period_end,
        trades: data.trades.filter((t) => t.direction === "short"),
        equity,
        drawdown,
        breakdown: data.short,
        allowAlpha: false,
      },
    ];
  }

  return [full, ...collectCalendarSlices(data, equity, drawdown)];
}

function periodMeta(d: Date): { id: string; start: string; end: string; label: string } {
  const y = d.getUTCFullYear();
  return { id: String(y), start: `${y}-01-01`, end: `${y}-12-31`, label: String(y) };
}

function collectCalendarSlices(
  data: TearsheetData,
  equity: TearsheetSeriesPoint[],
  drawdown: TearsheetSeriesPoint[],
): StatSlice[] {
  const periodKeys = new Map<string, { start: string; end: string; label: string }>();

  const addDate = (iso: string) => {
    const meta = periodMeta(new Date(iso));
    if (!periodKeys.has(meta.id)) {
      periodKeys.set(meta.id, { start: meta.start, end: meta.end, label: meta.label });
    }
  };

  for (const p of equity) addDate(p.t);
  for (const t of data.trades) {
    const exit = t.exit_date || t.entry_date;
    if (exit) addDate(exit);
  }

  return [...periodKeys.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(([id, meta]) => ({
      id,
      label: meta.label,
      startISO: meta.start,
      endISO: meta.end,
      trades: tradesInRange(data.trades, meta.start, meta.end),
      equity: clipRange(equity, meta.start, meta.end),
      drawdown: clipRange(drawdown, meta.start, meta.end),
      allowAlpha: false,
    }));
}

export function computeSliceMetrics(slice: StatSlice, data: TearsheetData): SliceMetrics {
  const closed = closedTrades(slice.trades);
  const tradeExtras = breakdownTradeStats(slice.trades);

  const returnFromEquity = periodReturnPct(slice.equity);
  const breakdown =
    slice.breakdown ?? breakdownFromTrades(slice.trades, returnFromEquity);

  const returnPct =
    slice.id === "full" || slice.id === "all"
      ? data.net_profit_pct
      : slice.breakdown
        ? slice.breakdown.net_profit_pct
        : (returnFromEquity ?? breakdown.net_profit_pct);

  const maxDrawdownPct =
    slice.id === "full" || slice.id === "all"
      ? data.max_drawdown_pct
      : maxDrawdownInSlice(slice.drawdown);

  const wins = breakdown.wins;
  const losses = breakdown.losses;
  const winRatePct = breakdown.trades > 0 ? breakdown.percent_profitable : null;
  const profitFactor = breakdown.trades > 0 ? breakdown.profit_factor : null;

  const eqLen = slice.equity.length;
  const initial = eqLen > 0 ? slice.equity[0].v : data.initial_capital;
  const final = eqLen > 0 ? slice.equity[eqLen - 1].v : initial;

  const cagr =
    slice.id === "full" || slice.id === "all"
      ? cagrPct(data.initial_capital, data.final_equity, slice.startISO, slice.endISO)
      : returnPct !== null
        ? cagrPctFromGrowth(returnPct, slice.startISO, slice.endISO)
        : null;

  const useEquityRisk =
    slice.id !== "long" && slice.id !== "short" && slice.equity.length >= 2;
  const risk = useEquityRisk
    ? deriveRiskMetrics(
        slice.equity,
        slice.allowAlpha ? data.ohlc_bars?.map((b) => ({ t: b.t, c: b.c })) : undefined,
        initial,
        final,
        slice.startISO,
        slice.endISO,
        maxDrawdownPct ?? 0,
        returnPct ?? 0,
        slice.id === "full" || slice.id === "all"
          ? {
              sharpe: data.sharpe_ratio,
              sortino: data.sortino_ratio,
              calmar: data.calmar_ratio,
            }
          : undefined,
      )
    : {
        sharpe: null,
        sortino: null,
        calmar: null,
        omega: null,
        volatilityPct: null,
        alphaPct: null,
        recovery: recoveryFactor(returnPct ?? 0, maxDrawdownPct ?? 0),
      };

  return {
    returnPct,
    cagrPct: cagr,
    maxDrawdownPct,
    sharpe: risk.sharpe,
    sortino: risk.sortino,
    calmar: risk.calmar,
    omega: risk.omega,
    volatilityPct: risk.volatilityPct,
    recovery: risk.recovery,
    alphaPct: slice.allowAlpha ? risk.alphaPct : null,
    trades: breakdown.trades,
    wins,
    losses,
    winRatePct,
    profitFactor,
    avgTradePct: closed.length > 0 ? avgTradePct(closed.map((t) => t.pnl_pct)) : null,
    avgWinPct: tradeExtras.avgWinPct,
    avgLossPct: tradeExtras.avgLossPct,
    bestPct: tradeExtras.bestPct,
    worstPct: tradeExtras.worstPct,
  };
}

export const PIVOT_LABELS: Record<StatsPivot, string> = {
  direction: "Direction",
  year: "Year",
};
