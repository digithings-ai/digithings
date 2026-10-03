/**
 * digiquant Vela colors. Lock 8: teal up, red down.
 * These match `lib/chart-colors.ts` dark fallbacks. They are not TradingView
 * green/red and not the mock stylesheet's green/salmon.
 *
 * Inter and JetBrains Mono belong to the shell slice. The chart uses the
 * platform mono stack so this slice does not load a second font.
 */
import type { VelaSpikeBar } from '@/components/research/VelaSpikeChart';

export const DIGIQUANT_UP = '#3dd6c4'; // canon-allow: Vela up, chart-colors dark fallback
export const DIGIQUANT_DOWN = '#e5533e'; // canon-allow: Vela down, chart-colors dark fallback
export const DIGIQUANT_WARN = '#e0b341'; // canon-allow: Vela warn, chart-colors dark fallback

/** App canvas fallback when a token has not resolved yet (`--bg` dark). */
export const DIGIQUANT_CANVAS = '#0A0E0C'; // canon-allow: canvas before --bg resolves

export const DESK_CHART_FONT = 'ui-monospace, SFMono-Regular, Menlo, monospace';

/** Vela project page — the attribution link required by NOTICE.luxalgo-vela. */
export const VELA_PROJECT_URL = 'https://luxalgo.com/vela';

export interface DeskChartSurface {
  background: string;
  text: string;
  grid: string;
}

export interface DeskVelaTheme {
  background: string;
  textColor: string;
  gridColor: string;
  borderColor: string;
  upColor: string;
  downColor: string;
  fontFamily: string;
}

export function deskVelaTheme(surface: DeskChartSurface): DeskVelaTheme {
  return {
    background: surface.background,
    textColor: surface.text,
    gridColor: surface.grid,
    borderColor: surface.grid,
    upColor: DIGIQUANT_UP,
    downColor: DIGIQUANT_DOWN,
    fontFamily: DESK_CHART_FONT,
  };
}

/** Top-level `upColor` / `downColor` reach the candles. Theme up/down do not. */
export function deskVelaOptions(
  bars: readonly VelaSpikeBar[],
  timeframe: string,
  surface: DeskChartSurface,
): {
  data: Array<{ time: number; open: number; high: number; low: number; close: number; volume?: number }>;
  timeframe: string;
  theme: DeskVelaTheme;
  upColor: string;
  downColor: string;
  live: false;
  drawings: false;
} {
  return {
    data: bars.map((bar) => ({
      time: bar.t,
      open: bar.o,
      high: bar.h,
      low: bar.l,
      close: bar.c,
      ...(bar.v === undefined ? {} : { volume: bar.v }),
    })),
    timeframe,
    theme: deskVelaTheme(surface),
    upColor: DIGIQUANT_UP,
    downColor: DIGIQUANT_DOWN,
    live: false,
    drawings: false,
  };
}

export type DeskChartWheelAction = 'scroll-pane' | 'chart';

/**
 * Vertical wheel scrolls the pane column. Horizontal wheel stays on the chart.
 * Equal deltas stay on the chart so a diagonal gesture is not stolen.
 */
export function deskChartWheelAction(event: {
  deltaX: number;
  deltaY: number;
}): DeskChartWheelAction {
  if (Math.abs(event.deltaY) > Math.abs(event.deltaX)) return 'scroll-pane';
  return 'chart';
}
