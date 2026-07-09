/**
 * DEMO DATA ONLY (#1450) — deterministic filler series for the finance-charts
 * family, the exact LCG walks the reference specimens shipped with, so the
 * promoted charts render pixel-identical on the reference pages. Marketing /
 * catalog surfaces may pass these; anything showing real performance passes
 * its own series — the chart components take data via required props precisely
 * so demo numbers can never ship by omission.
 */

import type { FinanceSeriesPoint, OhlcPoint } from "./chart-host";
import type { MonthlyReturnRow } from "./MonthlyReturns";

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

/** Cumulative-equity walk: starts at 100, drifts up with dips (weekly bars). */
function equityCurveDemo(n: number): FinanceSeriesPoint[] {
  const rnd = lcg(730217);
  const start = new Date(Date.UTC(2022, 0, 1));
  const data: FinanceSeriesPoint[] = [];
  let equity = 100;
  for (let i = 0; i < n; i++) {
    equity *= 1 + (rnd() - 0.44) * 0.05;
    data.push({ time: isoOffset(start, i * 7), value: Math.max(40, equity) });
  }
  return data;
}

/** Underwater curve: % below the running peak of an equity walk — every
 *  value is ≤ 0. */
function drawdownDemo(n: number): FinanceSeriesPoint[] {
  const rnd = lcg(5150);
  const start = new Date(Date.UTC(2022, 0, 1));
  const data: FinanceSeriesPoint[] = [];
  let equity = 100;
  let peak = 100;
  for (let i = 0; i < n; i++) {
    equity *= 1 + (rnd() - 0.44) * 0.05;
    peak = Math.max(peak, equity);
    data.push({
      time: isoOffset(start, i * 7),
      value: Math.round((equity / peak - 1) * 1000) / 10,
    });
  }
  return data;
}

/** Daily OHLC + volume walk. */
function priceChartDemo(n: number): { candles: OhlcPoint[]; volume: FinanceSeriesPoint[] } {
  const rnd = lcg(20260101);
  const start = new Date(Date.UTC(2026, 0, 1));
  const candles: OhlcPoint[] = [];
  const volume: FinanceSeriesPoint[] = [];
  let price = 92;
  for (let i = 0; i < n; i++) {
    const time = isoOffset(start, i);
    const drift = (rnd() - 0.47) * 3.4;
    const open = price;
    const close = Math.max(6, open + drift);
    const high = Math.max(open, close) + rnd() * 2.1;
    const low = Math.min(open, close) - rnd() * 2.1;
    candles.push({ time, open, high, low, close });
    volume.push({ time, value: 40 + rnd() * 120 });
    price = close;
  }
  return { candles, volume };
}

/** Monthly % returns 2022–2026, the last year only through June. */
function monthlyReturnsDemo(): MonthlyReturnRow[] {
  const rnd = lcg(9973);
  return [2022, 2023, 2024, 2025, 2026].map((year) => {
    const values = Array.from({ length: 12 }, (_, m) => {
      if (year === 2026 && m > 5) return null;
      return Math.round((rnd() - 0.42) * 24 * 10) / 10;
    });
    return { year, values };
  });
}

/** Demo cumulative-equity series (210 weekly points from 2022-01-01). */
export const EQUITY_CURVE_DEMO: FinanceSeriesPoint[] = equityCurveDemo(210);

/** Demo underwater-drawdown series (210 weekly points, all ≤ 0). */
export const DRAWDOWN_DEMO: FinanceSeriesPoint[] = drawdownDemo(210);

/** Demo OHLC candles + volume bars (120 daily points from 2026-01-01). */
export const PRICE_CHART_DEMO: { candles: OhlcPoint[]; volume: FinanceSeriesPoint[] } =
  priceChartDemo(120);

/** Demo monthly-returns heatmap rows (2022–2026, 2026 through June). */
export const MONTHLY_RETURNS_DEMO: MonthlyReturnRow[] = monthlyReturnsDemo();
