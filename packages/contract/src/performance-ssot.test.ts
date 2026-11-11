import { describe, expect, it } from "vitest";
import {
  calendarDaysBetween,
  persistedHeadlinesFromNav,
  persistedInsightMetrics,
} from "./performance-ssot";

/**
 * Runtime edge check for the package boundary: `performance-ssot` is the only
 * module in this package that reaches into `@digithings-ai/perf-math`, so a broken
 * or React-carrying resolution there fails here rather than in a Worker bundle.
 */
describe("performance SSOT over @digithings-ai/perf-math", () => {
  const nav = [
    { date: "2026-01-02", nav: 100 },
    { date: "2026-01-05", nav: 101, day_return_pct: 1 },
    { date: "2026-01-06", nav: 102.01, day_return_pct: 1 },
  ];

  it("derives persisted headlines from an accounting NAV series", () => {
    const headlines = persistedHeadlinesFromNav(nav);
    expect(headlines.sinceInceptionPct).toBeCloseTo(2.01, 6);
    expect(headlines.sinceInceptionStartDate).toBe("2026-01-02");
    expect(headlines.dayReturnPct).toBeCloseTo(1, 6);
    expect(headlines.navAsOf).toBe("2026-01-06");
  });

  it("returns null insight metrics when no benchmark series is supplied", () => {
    expect(persistedInsightMetrics(nav, undefined)).toEqual({
      excessReturnPct: null,
      alphaPct: null,
      informationRatio: null,
    });
  });

  it("counts calendar days between UTC stamps", () => {
    expect(calendarDaysBetween("2026-01-05", "2026-01-06")).toBe(1);
    expect(calendarDaysBetween("2026-1-5", "2026-01-06")).toBeNull();
  });
});
