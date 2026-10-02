import { describe, expect, it } from "vitest";
import {
  BUILD_COLUMNS,
  BUILD_DONE_MS,
  BUILD_RISE_MS,
  BUILD_START_MS,
  BARS_START_MS,
  BARS_SWEEP_MS,
  CHART_BUILD_MAX_MS,
  CHART_BUILD_TARGET_MS,
  CHART_INTRO_MS,
  CHROME_DONE_MS,
  COPY_DONE_MS,
  HANDOFF_MS,
  INDICATOR_SWEEP_MS,
  PHASE_SUM_MS,
  buildProgress,
  columnDelayMs,
  sweepDelayMs,
} from "./hero-build";

describe("hero build clock", () => {
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
    expect(BARS_START_MS).toBeGreaterThanOrEqual(600);
    expect(BARS_START_MS).toBeLessThanOrEqual(1000);
    expect(BARS_SWEEP_MS).toBe(2000);
    expect(INDICATOR_SWEEP_MS).toBe(1200);
    expect(PHASE_SUM_MS).toBeGreaterThanOrEqual(CHART_BUILD_TARGET_MS - 400);
    expect(PHASE_SUM_MS).toBeLessThanOrEqual(CHART_BUILD_TARGET_MS + 200);
    expect(PHASE_SUM_MS).toBeLessThan(CHART_BUILD_MAX_MS);
    expect(COPY_DONE_MS + BARS_START_MS + BARS_SWEEP_MS).toBeLessThan(CHART_BUILD_MAX_MS);
  });
});
