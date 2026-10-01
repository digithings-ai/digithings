import { describe, expect, it } from "vitest";
import {
  BUILD_COLUMNS,
  BUILD_DONE_MS,
  BUILD_RISE_MS,
  BUILD_START_MS,
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
});
