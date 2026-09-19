/**
 * DEMO DATA ONLY (#1463) — one deterministic backtest for the
 * finance-tearsheet reference specimens: a three-year daily OHLC walk, a
 * long/short trade log marked on it (last leg open), and the
 * mark-to-market equity / underwater curves those trades imply. Same LCG
 * doctrine as the finance-charts demos: stable across renders and runtimes,
 * and the components take data via required props precisely so demo numbers
 * can never ship by omission.
 */
import type {
  TearsheetOhlcBar,
  TearsheetSeriesPoint,
  TearsheetTrade,
  TradeReturnBar,
} from "./types";

/** Deterministic LCG in [0, 1) — stable across renders and runtimes. */
function lcg(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) & 0x7fffffff;
    return s / 0x7fffffff;
  };
}

function isoOffset(startUtc: Date, days: number): string {
  const date = new Date(startUtc);
  date.setUTCDate(startUtc.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

const N_BARS = 780;
const START = new Date(Date.UTC(2023, 0, 2));

function ohlcDemo(): TearsheetOhlcBar[] {
  const rnd = lcg(1463);
  const bars: TearsheetOhlcBar[] = [];
  let price = 68;
  for (let i = 0; i < N_BARS; i++) {
    // Regime-y drift: slow sine bias + noise, so trends exist for trades to ride.
    const bias = Math.sin(i / 90) * 0.008 + 0.0008;
    const o = price;
    const c = Math.max(9, o * (1 + bias + (rnd() - 0.5) * 0.045));
    const h = Math.max(o, c) * (1 + rnd() * 0.014);
    const l = Math.min(o, c) * (1 - rnd() * 0.014);
    bars.push({ t: isoOffset(START, i), o, h, l, c });
    price = c;
  }
  return bars;
}

interface DemoBuild {
  bars: TearsheetOhlcBar[];
  trades: TearsheetTrade[];
  equity: TearsheetSeriesPoint[];
  drawdown: TearsheetSeriesPoint[];
  tradeReturnBars: TradeReturnBar[];
}

function build(): DemoBuild {
  const bars = ohlcDemo();
  const rnd = lcg(97031);
  const trades: TearsheetTrade[] = [];

  // Round trips over the bar walk: hold 12–60 bars, sit out 3–18, flip
  // direction with the local regime. The final leg stays open (marked to the
  // last close) so the open-trade grammar shows everywhere it exists.
  let i = 5;
  let n = 1;
  let equityMark = 100_000;
  while (i < N_BARS - 70) {
    const hold = 12 + Math.floor(rnd() * 48);
    const exitIdx = Math.min(N_BARS - 2, i + hold);
    const direction: "long" | "short" = Math.sin(i / 90) + (rnd() - 0.5) * 0.6 > 0 ? "long" : "short";
    const entry = bars[i].c;
    const exit = bars[exitIdx].c;
    const pnlPct = direction === "long" ? (exit / entry - 1) * 100 : (entry / exit - 1) * 100;
    const qty = Math.round((equityMark / entry) * 100) / 100;
    const pnl = equityMark * (pnlPct / 100);
    equityMark += pnl;
    trades.push({
      n,
      direction,
      entry_label: direction === "long" ? "breakout" : "fade",
      entry_date: bars[i].t,
      entry_price: entry,
      exit_date: bars[exitIdx].t,
      exit_price: exit,
      qty,
      pnl,
      pnl_pct: pnlPct,
      equity_after: equityMark,
      exit_reason: rnd() > 0.5 ? "signal" : "stop",
      max_runup_pct: Math.abs(pnlPct) * (1 + rnd() * 0.4),
      max_drawdown_pct: -Math.abs(pnlPct) * rnd() * 0.6,
    });
    n += 1;
    i = exitIdx + 3 + Math.floor(rnd() * 15);
  }

  // Open leg: enters near the end, marks to the last close.
  const lastBar = bars[N_BARS - 1];
  const openIdx = N_BARS - 40;
  const openEntry = bars[openIdx].c;
  const openPct = (lastBar.c / openEntry - 1) * 100;
  trades.push({
    n,
    direction: "long",
    entry_label: "breakout",
    entry_date: bars[openIdx].t,
    entry_price: openEntry,
    exit_date: "",
    exit_price: lastBar.c,
    qty: Math.round((equityMark / openEntry) * 100) / 100,
    pnl: equityMark * (openPct / 100),
    pnl_pct: openPct,
    equity_after: equityMark,
    exit_reason: "open",
    max_runup_pct: Math.max(0, openPct) * 1.2,
    max_drawdown_pct: Math.min(0, openPct) * 0.8,
  });

  // Mark-to-market equity: ride each trade's direction bar to bar, flat
  // between trades — the curve the KPIs, matrix, and drawdown derive from.
  const equity: TearsheetSeriesPoint[] = [];
  const drawdown: TearsheetSeriesPoint[] = [];
  let eq = 100_000;
  let peak = eq;
  let t = 0;
  for (let b = 0; b < N_BARS; b++) {
    const bar = bars[b];
    let active: TearsheetTrade | undefined;
    while (t < trades.length && bar.t >= trades[t].entry_date) {
      const exitT = trades[t].exit_date || lastBar.t;
      if (bar.t <= exitT) {
        active = trades[t];
        break;
      }
      t += 1;
    }
    if (b > 0 && active) {
      const barRet = bars[b].c / bars[b - 1].c - 1;
      eq *= 1 + (active.direction === "long" ? barRet : -barRet);
    }
    peak = Math.max(peak, eq);
    equity.push({ t: bar.t, v: eq });
    drawdown.push({ t: bar.t, v: Math.round((eq / peak - 1) * 1000) / 10 });
  }

  const closed = trades.filter((tr) => tr.exit_reason !== "open");
  const open = trades[trades.length - 1];
  const tradeReturnBars: TradeReturnBar[] = closed.map((tr) => ({
    t: tr.exit_date,
    pct: tr.pnl_pct,
    open: false,
    trade: tr,
  }));
  tradeReturnBars.push({ t: lastBar.t, pct: open.pnl_pct, open: true, trade: open });

  return { bars, trades, equity, drawdown, tradeReturnBars };
}

const BUILT = build();

/** The demo backtest the reference tearsheet specimens compose. */
export const TEARSHEET_DEMO = {
  symbol: "DGQ-USD",
  periodStart: BUILT.bars[0].t,
  periodEnd: BUILT.bars[BUILT.bars.length - 1].t,
  /** Shared x-span for the synced charts. */
  fullSpan: [BUILT.bars[0].t, BUILT.bars[BUILT.bars.length - 1].t] as [string, string],
  bars: BUILT.bars,
  trades: BUILT.trades,
  equity: BUILT.equity,
  drawdown: BUILT.drawdown,
  tradeReturnBars: BUILT.tradeReturnBars,
};
