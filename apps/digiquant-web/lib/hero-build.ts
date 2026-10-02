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

/** The hero chart fades in as one finished frame. It does not build bar by bar. */
export const HERO_FADE_MS = 700;

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

/**
 * Indicators start when the candle sweep ends (it has already begun) and travel
 * L→R on their own pass. Abutting the candle sweep — no gap, no silence pad.
 */
export const INDICATOR_SWEEP_MS = 1200;
export const INDICATOR_START_MS = BARS_SWEEP_MS;

/** Fallback if replay is unavailable — Vela intro grow (clamped by Vela to 5s). */
export const CHART_INTRO_MS = Math.min(BARS_SWEEP_MS, CHART_BUILD_MAX_MS);

/**
 * Scheduled phase sum (chrome + handoff + axes/grid + bars + indicators).
 * Indicator pass follows the candles (`INDICATOR_START_MS === BARS_SWEEP_MS`), so this
 * is also the wall-clock from first paint to the last stroke when the feed is on time.
 */
export const PHASE_SUM_MS =
  CHROME_DONE_MS + HANDOFF_MS + BARS_START_MS + BARS_SWEEP_MS + INDICATOR_SWEEP_MS;

/** Same instant as PHASE_SUM_MS: axes start + candle sweep + indicator sweep. */
export const CHART_BUILD_END_MS =
  COPY_DONE_MS + BARS_START_MS + INDICATOR_START_MS + INDICATOR_SWEEP_MS;

/** One hero bar. `time` is the open, epoch ms — the same clock Vela drawings use. */
export type HeroBar = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

export type HeroPoint = { time: number; price: number };

/** One left-to-right stroke. Gaps (SuperTrend flips) are separate strokes. */
export type HeroStroke = { color: string; points: HeroPoint[] };

export type HeroOverlay = "bollinger-bands" | "vwap" | "supertrend";

/** Match the native inputs QuantField adds when the sweep hands off. */
export const SMA_COLOR = "#E8F7FF";
export const EMA_COLOR = "#F5C16C";
export const SMA_LENGTH = 20;
export const EMA_LENGTH = 50;
const BB_BASIS = "#ff9800";
const BB_BAND = "#5b9cf6";
const LINE_UP = "#089981";
const LINE_DOWN = "#f23645";

function finiteRun(bars: readonly HeroBar[], values: readonly number[]): HeroPoint[][] {
  const runs: HeroPoint[][] = [];
  let cur: HeroPoint[] = [];
  for (let i = 0; i < bars.length; i++) {
    const price = values[i];
    if (!Number.isFinite(price)) {
      if (cur.length >= 2) runs.push(cur);
      cur = [];
      continue;
    }
    cur.push({ time: bars[i].time, price });
  }
  if (cur.length >= 2) runs.push(cur);
  return runs;
}

function smaValues(values: readonly number[], len: number): number[] {
  const out = new Array<number>(values.length).fill(Number.NaN);
  if (len <= 0) return out;
  for (let i = len - 1; i < values.length; i++) {
    let sum = 0;
    for (let k = i - len + 1; k <= i; k++) sum += values[k];
    out[i] = sum / len;
  }
  return out;
}

/** Vela's EMA: SMA seed over the first `len` closes, then `2/(len+1)`. */
function emaValues(values: readonly number[], len: number): number[] {
  const out = new Array<number>(values.length).fill(Number.NaN);
  if (len <= 0) return out;
  const alpha = 2 / (len + 1);
  let prev = Number.NaN;
  let run = 0;
  for (let i = 0; i < values.length; i++) {
    const x = values[i];
    if (!Number.isFinite(x)) {
      run = 0;
      prev = Number.NaN;
      continue;
    }
    run += 1;
    if (Number.isFinite(prev)) {
      prev = alpha * x + (1 - alpha) * prev;
      out[i] = prev;
    } else if (run >= len) {
      let sum = 0;
      for (let k = i - len + 1; k <= i; k++) sum += values[k];
      prev = sum / len;
      out[i] = prev;
    }
  }
  return out;
}

function stdevValues(values: readonly number[], len: number): number[] {
  const means = smaValues(values, len);
  const out = new Array<number>(values.length).fill(Number.NaN);
  for (let i = len - 1; i < values.length; i++) {
    const mean = means[i];
    if (!Number.isFinite(mean)) continue;
    let sq = 0;
    for (let k = i - len + 1; k <= i; k++) {
      const d = values[k] - mean;
      sq += d * d;
    }
    out[i] = Math.sqrt(sq / len);
  }
  return out;
}

function trueRange(bars: readonly HeroBar[]): number[] {
  const out = new Array<number>(bars.length).fill(Number.NaN);
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    if (i === 0) {
      out[i] = b.high - b.low;
      continue;
    }
    const prev = bars[i - 1].close;
    out[i] = Math.max(b.high - b.low, Math.abs(b.high - prev), Math.abs(b.low - prev));
  }
  return out;
}

function bollingerStrokes(bars: readonly HeroBar[]): HeroStroke[] {
  const src = bars.map((b) => b.close);
  const basis = smaValues(src, SMA_LENGTH);
  const dev = stdevValues(src, SMA_LENGTH);
  const upper = basis.map((b, i) => (Number.isFinite(b) && Number.isFinite(dev[i]) ? b + 2 * dev[i] : Number.NaN));
  const lower = basis.map((b, i) => (Number.isFinite(b) && Number.isFinite(dev[i]) ? b - 2 * dev[i] : Number.NaN));
  return [
    ...finiteRun(bars, basis).map((points) => ({ color: BB_BASIS, points })),
    ...finiteRun(bars, upper).map((points) => ({ color: BB_BAND, points })),
    ...finiteRun(bars, lower).map((points) => ({ color: BB_BAND, points })),
  ];
}

/** Session VWAP (UTC day), typical price, matching Vela's default anchor. */
function vwapStrokes(bars: readonly HeroBar[]): HeroStroke[] {
  const values = new Array<number>(bars.length).fill(Number.NaN);
  let period = Number.NaN;
  let cumPV = 0;
  let cumV = 0;
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    const key = Math.floor(b.time / 86_400_000);
    if (key !== period) {
      period = key;
      cumPV = 0;
      cumV = 0;
    }
    const vol = b.volume;
    if (vol != null && Number.isFinite(vol) && vol > 0) {
      const tp = (b.high + b.low + b.close) / 3;
      cumPV += tp * vol;
      cumV += vol;
    }
    if (cumV > 0) values[i] = cumPV / cumV;
  }
  return finiteRun(bars, values).map((points) => ({ color: LINE_UP, points }));
}

/** Wilder SuperTrend, ATR 10 × 3 — the same recurrence Vela's native uses. */
function supertrendStrokes(bars: readonly HeroBar[]): HeroStroke[] {
  const tr = trueRange(bars);
  const atr = new Array<number>(bars.length).fill(Number.NaN);
  const alpha = 1 / 10;
  let prev = Number.NaN;
  let run = 0;
  for (let i = 0; i < tr.length; i++) {
    const x = tr[i];
    if (!Number.isFinite(x)) {
      run = 0;
      prev = Number.NaN;
      continue;
    }
    run += 1;
    if (Number.isFinite(prev)) {
      prev = alpha * x + (1 - alpha) * prev;
      atr[i] = prev;
    } else if (run >= 10) {
      let sum = 0;
      for (let k = i - 9; k <= i; k++) sum += tr[k];
      prev = sum / 10;
      atr[i] = prev;
    }
  }
  const up = new Array<number>(bars.length).fill(Number.NaN);
  const down = new Array<number>(bars.length).fill(Number.NaN);
  let finalUpper = Number.NaN;
  let finalLower = Number.NaN;
  let trend = -1;
  for (let i = 0; i < bars.length; i++) {
    const r = atr[i];
    if (!Number.isFinite(r)) continue;
    const b = bars[i];
    const mid = (b.high + b.low) / 2;
    const basicUpper = mid + 3 * r;
    const basicLower = mid - 3 * r;
    const prevUpper = Number.isFinite(finalUpper) ? finalUpper : basicUpper;
    const prevLower = Number.isFinite(finalLower) ? finalLower : basicLower;
    const prevClose = i > 0 ? bars[i - 1].close : b.close;
    finalUpper = prevClose <= prevUpper ? Math.min(basicUpper, prevUpper) : basicUpper;
    finalLower = prevClose >= prevLower ? Math.max(basicLower, prevLower) : basicLower;
    trend = b.close > finalUpper ? 1 : b.close < finalLower ? -1 : trend;
    if (trend === 1) up[i] = finalLower;
    else down[i] = finalUpper;
  }
  return [
    ...finiteRun(bars, up).map((points) => ({ color: LINE_UP, points })),
    ...finiteRun(bars, down).map((points) => ({ color: LINE_DOWN, points })),
  ];
}

/** Native-indicator inputs that match `heroIndicatorStrokes` for this overlay. */
export function heroOverlayInputs(overlay: HeroOverlay): Record<string, number | string | boolean> {
  if (overlay === "bollinger-bands") {
    return { length: SMA_LENGTH, mult: 2, basisColor: BB_BASIS, color: BB_BAND, fillColor: "rgba(0,0,0,0)" };
  }
  if (overlay === "supertrend") {
    return { atrLength: 10, mult: 3, upColor: LINE_UP, downColor: LINE_DOWN };
  }
  return {
    anchor: "Session",
    source: "HLC3",
    bullColor: LINE_UP,
    bearColor: LINE_UP,
    band1: false,
    fill: false,
  };
}

/**
 * SMA 20, EMA 50, and one overlay, as strokes that can be revealed by bar index.
 * Points are in time order. A stroke never bridges a gap.
 */
export function heroIndicatorStrokes(bars: readonly HeroBar[], overlay: HeroOverlay): HeroStroke[] {
  const src = bars.map((b) => b.close);
  const strokes: HeroStroke[] = [
    ...finiteRun(bars, smaValues(src, SMA_LENGTH)).map((points) => ({ color: SMA_COLOR, points })),
    ...finiteRun(bars, emaValues(src, EMA_LENGTH)).map((points) => ({ color: EMA_COLOR, points })),
  ];
  if (overlay === "bollinger-bands") strokes.push(...bollingerStrokes(bars));
  else if (overlay === "vwap") strokes.push(...vwapStrokes(bars));
  else strokes.push(...supertrendStrokes(bars));
  return strokes;
}

/** Points of `stroke` whose bar is at or before `index` in `bars` (inclusive). */
export function revealStroke(stroke: HeroStroke, bars: readonly HeroBar[], index: number): HeroPoint[] {
  if (bars.length === 0 || stroke.points.length === 0) return [];
  const i = Math.max(0, Math.min(bars.length - 1, index));
  const cutoff = bars[i].time;
  const out: HeroPoint[] = [];
  for (const point of stroke.points) {
    if (point.time > cutoff) break;
    out.push(point);
  }
  return out;
}

/** Fixed plot: first bar on the left, one bar of pad on the right. */
export function candleSweepRange(
  first: number,
  last: number,
  barMs: number,
): { from: number; to: number } {
  return { from: first, to: last + barMs };
}

export type LockedDomain = {
  priceMin: number;
  priceMax: number;
  volumeMax: number;
};

/** Y extremes of the complete series, including the overlay on the finished chart. */
export function finalSeriesDomain(bars: readonly HeroBar[], overlay?: HeroOverlay): LockedDomain {
  let priceMin = Number.POSITIVE_INFINITY;
  let priceMax = Number.NEGATIVE_INFINITY;
  let volumeMax = 0;
  const consider = (value: number) => {
    if (!Number.isFinite(value)) return;
    if (value < priceMin) priceMin = value;
    if (value > priceMax) priceMax = value;
  };
  for (const bar of bars) {
    consider(bar.low);
    consider(bar.high);
    if (bar.volume != null && bar.volume > volumeMax) volumeMax = bar.volume;
  }
  if (overlay && bars.length > 0) {
    for (const stroke of heroIndicatorStrokes(bars, overlay)) {
      for (const point of stroke.points) consider(point.price);
    }
  }
  if (priceMin === Number.POSITIVE_INFINITY || priceMax === Number.NEGATIVE_INFINITY) {
    return { priceMin: 0, priceMax: 1, volumeMax };
  }
  return { priceMin, priceMax, volumeMax };
}

export function revealYDomain(
  bars: readonly HeroBar[],
  revealedCount: number,
  overlay?: HeroOverlay,
): LockedDomain {
  void revealedCount;
  return finalSeriesDomain(bars, overlay);
}

export function paddedPriceWindow(
  domain: LockedDomain,
  margins: { top: number; bottom: number } = { top: 10, bottom: 10 },
): { min: number; max: number } {
  const { priceMin: min, priceMax: max } = domain;
  if (!(max > min)) {
    const pad = Math.abs(min) * 0.1 || 1;
    return { min: min - pad, max: max + pad };
  }
  const content = Math.max(0.1, 1 - (margins.top + margins.bottom) / 100);
  const above = margins.top / 100 / content;
  const below = margins.bottom / 100 / content;
  const span = max - min;
  return { min: min - span * below, max: max + span * above };
}
