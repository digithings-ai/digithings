import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  BUILD_COLUMNS,
  BUILD_DONE_MS,
  BUILD_RISE_MS,
  BUILD_START_MS,
  BARS_START_MS,
  BARS_SWEEP_MS,
  CHART_BUILD_MAX_MS,
  HERO_FADE_MS,
  CHART_BUILD_TARGET_MS,
  CHART_INTRO_MS,
  CHART_BUILD_END_MS,
  CHROME_DONE_MS,
  COPY_DONE_MS,
  HANDOFF_MS,
  INDICATOR_START_MS,
  INDICATOR_SWEEP_MS,
  PHASE_SUM_MS,
  buildProgress,
  AXIS_X_MS,
  AXIS_Y_MS,
  AXIS_Y_START_MS,
  candleSweepClip,
  candleSweepRange,
  columnDelayMs,
  finalSeriesDomain,
  INDICATOR_LAG_MS,
  paddedPriceWindow,
  revealYDomain,
  staggerReveal,
  VOLUME_LAG_MS,
  heroIndicatorStrokes,
  revealStroke,
  sweepDelayMs,
  type HeroBar,
} from "./hero-build";

describe("hero build clock", () => {
  it("fades the finished chart in instead of building it", () => {
    expect(HERO_FADE_MS).toBeGreaterThan(200);
    expect(HERO_FADE_MS).toBeLessThan(1200);
    expect(HERO_FADE_MS).toBeLessThan(CHART_BUILD_MAX_MS);
  });

  it("sweeps from the first wordmark column to the last", () => {
    expect(BUILD_COLUMNS).toBe(79);
    expect(sweepDelayMs(0)).toBe(BUILD_START_MS);
    expect(sweepDelayMs(1)).toBe(columnDelayMs(BUILD_COLUMNS - 1));
    expect(sweepDelayMs(-1)).toBe(sweepDelayMs(0));
    expect(sweepDelayMs(2)).toBe(sweepDelayMs(1));
  });

  it("starts a candle exactly when the wordmark column at the same fraction starts", () => {
    expect(sweepDelayMs(0.5)).toBeCloseTo(columnDelayMs((BUILD_COLUMNS - 1) / 2));
  });

  it("draws nothing before the build and everything after it", () => {
    expect(buildProgress(0, 0.5)).toBe(0);
    expect(buildProgress(BUILD_DONE_MS, 1)).toBe(1);
    expect(buildProgress(BUILD_DONE_MS + 5000, 0)).toBe(1);
  });

  it("pins the candle frame so a playhead zoom or right-to-left window fails", () => {
    const barMs = 60_000;
    const first = 1_700_000_000_000;
    const last = first + 180 * barMs;
    const cursor = first + 12 * barMs;
    const frame = candleSweepRange(first, last, barMs);
    const followCursor = { from: first, to: cursor + barMs };
    const rightToLeft = { from: last - (cursor - first), to: last + barMs };
    expect(frame).not.toEqual(followCursor);
    expect(frame).not.toEqual(rightToLeft);
    expect(frame.from).toBe(first);
    expect(frame.to).toBe(last + barMs);
    const shown = (cursor - frame.from) / (frame.to - frame.from);
    expect(shown).toBeGreaterThan(0);
    expect(shown).toBeLessThan(0.15);
    expect(frame.from).toBeLessThan(rightToLeft.from);
  });

  it("locks the Y domain to the full series while bars reveal", () => {
    const bars: HeroBar[] = Array.from({ length: 60 }, (_, i) => {
      const close = i < 50 ? 200 : 80;
      return {
        time: 1_700_000_000_000 + i * 60_000,
        open: close - 0.4,
        high: i === 59 ? 420 : close + 0.6,
        low: i === 59 ? 40 : close - 0.6,
        close,
        volume: i === 59 ? 9_000 : 12 + i,
      };
    });
    const full = finalSeriesDomain(bars);
    for (const shown of [1, 4, 30, 59]) {
      expect(revealYDomain(bars, shown)).toEqual(full);
      expect(paddedPriceWindow(revealYDomain(bars, shown))).toEqual(paddedPriceWindow(full));
    }
    const prefix = finalSeriesDomain(bars.slice(0, 4));
    expect(prefix.priceMin).toBeGreaterThan(full.priceMin);
    expect(prefix.priceMax).toBeLessThan(full.priceMax);
    expect(prefix.volumeMax).toBeLessThan(full.volumeMax);
    expect(revealYDomain(bars, 1).priceMax).toBe(full.priceMax);
    expect(revealYDomain(bars, 1).volumeMax).toBe(full.volumeMax);
    const n = bars.length;
    for (const elapsed of [0, 180, 800, 1400, BARS_SWEEP_MS]) {
      const layer = staggerReveal(elapsed, n);
      expect(revealYDomain(bars, layer.candles)).toEqual(full);
      expect(revealYDomain(bars, layer.indicators)).toEqual(full);
      expect(revealYDomain(bars, layer.volume).volumeMax).toBe(full.volumeMax);
      expect(layer.indicators).toBeLessThanOrEqual(layer.candles);
      expect(layer.volume).toBeLessThanOrEqual(layer.candles);
      if (layer.candles < n) expect(layer.volume).toBeLessThan(layer.candles);
    }
    const early = staggerReveal(120, n);
    expect(early.candles).toBeGreaterThan(0);
    expect(early.indicators).toBe(0);
    expect(early.volume).toBe(0);
    const mid = staggerReveal(BARS_SWEEP_MS * 0.55, n);
    expect(mid.candles).toBeGreaterThan(mid.indicators);
    expect(mid.indicators).toBeGreaterThan(mid.volume);
    expect(mid.volume).toBeGreaterThan(0);
    expect(INDICATOR_LAG_MS).toBeGreaterThan(0);
    expect(INDICATOR_LAG_MS).toBeLessThan(BARS_SWEEP_MS);
    expect(VOLUME_LAG_MS).toBeGreaterThan(INDICATOR_LAG_MS);
    expect(VOLUME_LAG_MS).toBeLessThan(BARS_SWEEP_MS);
  });

  it("uncovers candles from the left edge and keeps the right side hidden", () => {
    expect(candleSweepClip(0)).toBe("inset(0 100% 0 0)");
    expect(candleSweepClip(BARS_SWEEP_MS / 2)).toBe("inset(0 50% 0 0)");
    expect(candleSweepClip(BARS_SWEEP_MS / 2)).not.toBe("inset(0 0 0 50%)");
    expect(candleSweepClip(BARS_SWEEP_MS)).toBe("");
    expect(candleSweepClip(BARS_SWEEP_MS + 400)).toBe("");
  });

  it("builds left to right at any moment", () => {
    const t = BUILD_START_MS + 300;
    const [a, b, c] = [0.1, 0.5, 0.9].map((f) => buildProgress(t, f));
    expect(a).toBeGreaterThan(b);
    expect(b).toBeGreaterThanOrEqual(c);
    expect(buildProgress(sweepDelayMs(0.3) + BUILD_RISE_MS / 2, 0.3)).toBeGreaterThan(0.5);
  });

  it("hands off to axes soon after chrome, not after the full wordmark", () => {
    expect(COPY_DONE_MS).toBeLessThan(BUILD_DONE_MS);
    expect(CHROME_DONE_MS).toBeGreaterThanOrEqual(600);
    expect(CHROME_DONE_MS).toBeLessThanOrEqual(900);
    expect(HANDOFF_MS).toBeLessThan(300);
    expect(COPY_DONE_MS).toBe(CHROME_DONE_MS + HANDOFF_MS);
    expect(CHART_INTRO_MS).toBeGreaterThan(1000);
  });

  it("keeps the chart construct near the 5s target and under the 10s cap", () => {
    expect(AXIS_Y_START_MS).toBeGreaterThan(0);
    expect(AXIS_Y_START_MS).toBeLessThan(AXIS_X_MS);
    expect(BARS_START_MS).toBeGreaterThan(AXIS_Y_START_MS);
    expect(BARS_START_MS).toBeLessThan(AXIS_Y_START_MS + AXIS_Y_MS);
    expect(BARS_SWEEP_MS).toBe(2400);
    expect(INDICATOR_SWEEP_MS).toBe(BARS_SWEEP_MS);
    expect(INDICATOR_START_MS).toBe(INDICATOR_LAG_MS);
    expect(INDICATOR_START_MS).toBeLessThan(BARS_SWEEP_MS);
    expect(HANDOFF_MS).toBeLessThan(300);
    expect(PHASE_SUM_MS).toBe(CHART_BUILD_END_MS);
    expect(PHASE_SUM_MS).toBeGreaterThanOrEqual(CHART_BUILD_TARGET_MS - 400);
    expect(PHASE_SUM_MS).toBeLessThanOrEqual(CHART_BUILD_TARGET_MS + 200);
    expect(PHASE_SUM_MS).toBeLessThan(CHART_BUILD_MAX_MS);
    expect(COPY_DONE_MS + BARS_START_MS + BARS_SWEEP_MS).toBeLessThan(CHART_BUILD_MAX_MS);
    expect(CHART_BUILD_END_MS).toBeLessThan(CHART_BUILD_MAX_MS);
  });

  it("reveals indicator strokes left to right, one pass", () => {
    const bars: HeroBar[] = Array.from({ length: 80 }, (_, i) => {
      const close = 100 + Math.sin(i / 4) * 8 + i * 0.15;
      return {
        time: 1_700_000_000_000 + i * 60_000,
        open: close - 0.4,
        high: close + 1.2,
        low: close - 1.1,
        close,
        volume: 10 + (i % 5),
      };
    });
    for (const overlay of ["bollinger-bands", "vwap", "supertrend"] as const) {
      const strokes = heroIndicatorStrokes(bars, overlay);
      expect(strokes.length).toBeGreaterThanOrEqual(2);
      for (const stroke of strokes) {
        expect(stroke.points.length).toBeGreaterThanOrEqual(2);
        for (let i = 1; i < stroke.points.length; i++) {
          expect(stroke.points[i].time).toBeGreaterThan(stroke.points[i - 1].time);
        }
        const early = revealStroke(stroke, bars, 30);
        const late = revealStroke(stroke, bars, bars.length - 1);
        expect(late.length).toBeGreaterThanOrEqual(early.length);
        expect(late.length).toBe(stroke.points.length);
      }
    }
    const bb = heroIndicatorStrokes(bars, "bollinger-bands");
    const basis = bb.find((s) => s.color === "#ff9800");
    const band = bb.find((s) => s.color === "#5b9cf6");
    expect(basis).toBeDefined();
    expect(band).toBeDefined();
    if (basis && band) {
      const at = basis.points[basis.points.length - 1];
      const upper = band.points.find((p) => p.time === at.time);
      expect(upper).toBeDefined();
      if (upper) expect(upper.price).not.toBeCloseTo(at.price, 6);
    }
  });
});
