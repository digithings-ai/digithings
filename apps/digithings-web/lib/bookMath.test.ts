import { describe, expect, it } from "vitest";

import { windowAlpha, windowBeta, type DrawnPoint } from "./bookMath";

function leg(dates: string[], values: number[]): DrawnPoint[] {
  return dates.map((t, i) => ({ t, v: values[i] }));
}

const DATES = ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"];

describe("windowBeta", () => {
  it("returns 1 when the portfolio tracks the benchmark exactly", () => {
    const bench = leg(DATES, [0, 10, 21, 32.1]);
    expect(windowBeta(bench, bench)).toBeCloseTo(1, 10);
  });

  it("returns 2 when the portfolio moves twice the benchmark daily", () => {
    // Benchmark dailies +10%, +5%, +8%; portfolio exactly 2x each day.
    const bench = leg(DATES, [0, 10, 15.5, 24.74]);
    const port = leg(DATES, [0, 20, 32, 53.12]);
    expect(windowBeta(port, bench)).toBeCloseTo(2, 6);
  });

  it("returns null when the window is too thin or the legs never overlap", () => {
    expect(windowBeta(leg(DATES.slice(0, 2), [0, 1]), leg(DATES.slice(0, 2), [0, 1]))).toBeNull();
    expect(
      windowBeta(leg(DATES, [0, 1, 2, 3]), leg(["2020-01-01", "2020-01-02"], [0, 1])),
    ).toBeNull();
  });

  it("returns null when the benchmark never moves", () => {
    const flat = leg(DATES, [5, 5, 5, 5]);
    const port = leg(DATES, [0, 1, 2, 3]);
    expect(windowBeta(port, flat)).toBeNull();
  });
});

describe("windowAlpha", () => {
  it("is the portfolio return minus beta times the benchmark return", () => {
    // Rp +44%, Rm +21%, beta 2 → 44 − 42 = +2 pts.
    expect(windowAlpha(44, 21, 2)).toBeCloseTo(2, 10);
  });

  it("is null when any input is missing", () => {
    expect(windowAlpha(null, 21, 2)).toBeNull();
    expect(windowAlpha(44, null, 2)).toBeNull();
    expect(windowAlpha(44, 21, null)).toBeNull();
  });
});
