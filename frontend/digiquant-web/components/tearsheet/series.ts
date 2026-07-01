import { type OHLCBar, type TearsheetPoint } from "./types";

/** True when `iso` is on or after `startISO` (calendar compare via epoch). */
export function onOrAfterDate(iso: string, startISO: string): boolean {
  if (!startISO) return true;
  return new Date(iso).getTime() >= new Date(startISO).getTime();
}

/** Drop points before the backtest / trade window. */
export function clipPoints(points: TearsheetPoint[], periodStart: string): TearsheetPoint[] {
  if (!periodStart || points.length === 0) return points;
  return points.filter((p) => onOrAfterDate(p.t, periodStart));
}

/** Drop OHLC bars before the backtest / trade window. */
export function clipOhlc(bars: OHLCBar[], periodStart: string): OHLCBar[] {
  if (!periodStart || bars.length === 0) return bars;
  return bars.filter((b) => onOrAfterDate(b.t, periodStart));
}

/** Shared x-span for linked charts: backtest start → last equity point. */
export function chartFullSpan(
  periodStart: string,
  equity: TearsheetPoint[],
  periodEnd: string,
): [string, string] | undefined {
  if (!periodStart) return undefined;
  const clipped = clipPoints(equity, periodStart);
  if (clipped.length === 0) return undefined;
  const end = clipped[clipped.length - 1].t || periodEnd;
  return [periodStart, end];
}
