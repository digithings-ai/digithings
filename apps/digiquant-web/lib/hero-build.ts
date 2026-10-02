/** Shared clock for the hero's build-in. The wordmark's pixel columns and the chart's
 *  construct both use this module; wordmark columns still rise on BUILD_* below. */

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
 * Chrome (logo + title + buttons) readable on screen. Matches `.hero-rise` settle
 * (~0.12s + stagger + 0.55s) rounded to the plan's ~0.7s chrome beat. Wordmark last
 * cells may still be rising — do not wait on BUILD_DONE_MS.
 */
export const CHROME_DONE_MS = 700;
/** Gap from chrome readable → axes start. Must stay under 300ms. */
export const HANDOFF_MS = 200;
export const COPY_DONE_MS = CHROME_DONE_MS + HANDOFF_MS;

/** Whole sequence target (~5s) and hard ceiling from first paint (10s). */
export const CHART_BUILD_TARGET_MS = 5000;
export const CHART_BUILD_MAX_MS = 10000;

/**
 * Axes then grid (~0.8s): X L→R, Y B→T (overlaps end of X), then faint grid.
 * Times are relative to construct t0 (axes start), not first paint.
 */
export const AXIS_X_MS = 320;
export const AXIS_Y_MS = 280;
export const AXIS_Y_START_MS = 240;
export const GRID_MS = 200;
export const GRID_START_MS = AXIS_Y_START_MS + AXIS_Y_MS;
export const BARS_START_MS = GRID_START_MS + GRID_MS;

/** Candles + volume L→R together after axes/grid. */
export const BARS_SWEEP_MS = 2000;

/** Indicators L→R; added at bars start so replay reveals them with the candles. */
export const INDICATOR_SWEEP_MS = 1200;
export const INDICATOR_START_MS = 0;

/** Fallback if replay is unavailable — Vela intro grow (clamped by Vela to 5s). */
export const CHART_INTRO_MS = Math.min(BARS_SWEEP_MS, CHART_BUILD_MAX_MS);

/**
 * Scheduled phase sum (chrome + handoff + axes/grid + bars + indicators).
 * Wall-clock is shorter when indicators overlap the candle sweep; do not pad silence.
 */
export const PHASE_SUM_MS =
  CHROME_DONE_MS + HANDOFF_MS + BARS_START_MS + BARS_SWEEP_MS + INDICATOR_SWEEP_MS;
