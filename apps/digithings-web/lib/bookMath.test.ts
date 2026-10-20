import { describe, expect, it } from "vitest";

import {
  fmtRatio,
  windowAlpha,
  windowBeta,
  windowInfoRatio,
  windowSharpe,
  windowSortino,
  type DrawnPoint,
} from "./bookMath";

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

// Five sessions, dailies +2%, +1.96%, +1.92%, −0.94% (node-verified).
const WEEK = ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"];
const WEEK_PORT = leg(WEEK, [0, 2, 4, 6, 5]);
const WEEK_BENCH = leg(WEEK, [0, 1, 2, 3, 2.5]);

describe("windowSharpe", () => {
  it("annualizes mean over stdev on 252 trading days", () => {
    expect(windowSharpe(WEEK_PORT)).toBeCloseTo(15.585, 3);
  });

  it("is null when too thin or the leg never varies", () => {
    expect(windowSharpe(leg(WEEK.slice(0, 1), [0]))).toBeNull();
    expect(windowSharpe(leg(WEEK.slice(0, 2), [0, 1]))).toBeNull();
    // Exactly flat: zero variance.
    expect(windowSharpe(leg(WEEK.slice(0, 4), [5, 5, 5, 5]))).toBeNull();
  });
});

describe("windowSortino", () => {
  it("annualizes mean over downside deviation on 252 trading days", () => {
    expect(windowSortino(WEEK_PORT)).toBeCloseTo(41.5665, 3);
  });

  it("is null when too thin or never dips below zero", () => {
    expect(windowSortino(leg(WEEK.slice(0, 2), [0, 1]))).toBeNull();
    expect(windowSortino(leg(WEEK.slice(0, 4), [0, 1, 2.01, 3.0301]))).toBeNull();
  });
});

describe("windowInfoRatio", () => {
  it("annualizes the paired excess returns on 252 trading days", () => {
    expect(windowInfoRatio(WEEK_PORT, WEEK_BENCH)).toBeCloseTo(15.7389, 3);
  });

  it("is null when the legs never overlap or the excess never varies", () => {
    expect(
      windowInfoRatio(leg(WEEK, [0, 1, 2, 3, 4]), leg(["2020-01-01", "2020-01-02"], [0, 1])),
    ).toBeNull();
    expect(windowInfoRatio(WEEK_PORT, WEEK_PORT)).toBeNull();
  });
});

describe("fmtRatio", () => {
  it("signs two decimals, or an em dash when missing", () => {
    expect(fmtRatio(null)).toBe("—");
    expect(fmtRatio(1.5)).toBe("+1.50");
    expect(fmtRatio(-0.25)).toBe("−0.25");
    expect(fmtRatio(0)).toBe("0.00");
  });
});
