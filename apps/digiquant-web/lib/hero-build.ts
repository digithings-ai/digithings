/** Shared clock for the hero's build-in. The wordmark's pixel columns and the chart's candles
 *  both rise left to right on this schedule, so they build together: a candle at x% of the
 *  hero starts rising when the wordmark's column at x% of its width does. */

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

/** Elapsed time after which every candle has finished rising. */
export const BUILD_DONE_MS = sweepDelayMs(1) + BUILD_RISE_MS;
