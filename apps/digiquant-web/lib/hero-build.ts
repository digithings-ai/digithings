/** Shared clock for the hero's build-in. The wordmark's pixel columns and the chart's
 *  candles both rise left to right on this schedule (wordmark columns still use it). */

export const BUILD_WORD = "DIGIQUANT";
/** Pixel columns in the wordmark: nine glyphs of seven columns, two columns of gap between. */
export const BUILD_COLUMNS = BUILD_WORD.length * 9 - 2;
export const BUILD_START_MS = 250;
export const BUILD_COLUMN_MS = 16;
/** Mean rise time of one wordmark cell (it varies 260 to 480 ms per cell). */
export const BUILD_RISE_MS = 360;

/** When the wordmark column `col` (0-based) starts rising, in ms after the build began. */
export const columnDelayMs = (col: number) => BUILD_START_MS + col * BUILD_COLUMN_MS;

/** When a chart candle at horizontal fraction `f` (0 left edge, 1 right edge) starts rising. */
export const sweepDelayMs = (f: number) => columnDelayMs(Math.min(1, Math.max(0, f)) * (BUILD_COLUMNS - 1));

/** Eased 0..1 progress of the candle at fraction `f`, `elapsedMs` after the build began. */
export function buildProgress(elapsedMs: number, f: number): number {
  const t = Math.min(1, Math.max(0, (elapsedMs - sweepDelayMs(f)) / BUILD_RISE_MS));
  return 1 - Math.pow(1 - t, 3);
}

/** Elapsed time after which every wordmark cell has finished rising. */
export const BUILD_DONE_MS = sweepDelayMs(1) + BUILD_RISE_MS;

/**
 * Chrome (logo + title + buttons) settle before the chart construct starts.
 * Matches `.hero-rise` (~0.12s + 2×0.08s stagger + 0.55s) — deliberately shorter than
 * the full wordmark pixel build so the chart handoff does not feel idle.
 */
export const CHROME_DONE_MS = 880;
export const COPY_SETTLE_MS = 80;
export const COPY_DONE_MS = CHROME_DONE_MS + COPY_SETTLE_MS;

/** Whole chart construct target (~5s) and hard ceiling (10s). */
export const CHART_BUILD_TARGET_MS = 5000;
export const CHART_BUILD_MAX_MS = 10000;

/** Axis + grid preamble (X L→R, Y B→T, then grid). */
export const AXIS_X_MS = 520;
export const AXIS_Y_MS = 420;
export const GRID_FADE_MS = 280;
/** Y starts near the end of X so the total preamble stays tight. */
export const AXIS_Y_START_MS = 360;
export const GRID_START_MS = AXIS_Y_START_MS + AXIS_Y_MS;
export const BARS_START_MS = GRID_START_MS + GRID_FADE_MS;

/** L→R candle + volume sweep after axes/grid (fills the ~5s target). */
export const BARS_SWEEP_MS = Math.max(2800, CHART_BUILD_TARGET_MS - BARS_START_MS);

/** Fallback if replay is unavailable — Vela intro grow (clamped by Vela to 5s). */
export const CHART_INTRO_MS = Math.min(4800, CHART_BUILD_MAX_MS);

/** Indicators stream once bars are underway. */
export const INDICATOR_START_MS = Math.round(BARS_SWEEP_MS * 0.2);
export const INDICATOR_STAGGER_MS = 260;
