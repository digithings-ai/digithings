import { describe, expect, it } from "vitest";
import { computeLivePerformanceKpis } from "@digithings/web";
import { currentNavRun, findNavSeriesSeams, isNavSeriesSeam } from "./nav-seam";
import type { NavPoint } from "./types";

/**
 * Repro of the false Sep-8 legacy→finalized jump (#3767 / #3935). The landing
 * hook must rebase the series on the current source run before computing KPIs —
 * otherwise since-inception / day return bridge the seam.
 */
function seamSeries(): NavPoint[] {
  return [
    {
      date: "2026-09-06",
      nav: 100,
      cashPct: 20,
      investedPct: 80,
      dayReturnPct: null,
      source: "legacy_nav_history",
      contract: "legacy_estimate",
      seriesSeam: false,
    },
    {
      date: "2026-09-07",
      nav: 99.92,
      cashPct: 20,
      investedPct: 80,
      dayReturnPct: null,
      source: "legacy_nav_history",
      contract: "legacy_estimate",
      seriesSeam: false,
    },
    {
      date: "2026-09-08",
      nav: 110.74928206,
      cashPct: 20,
      investedPct: 80,
      dayReturnPct: null,
      source: "finalized_accounting",
      contract: "finalized_accounting",
      seriesSeam: true,
    },
    {
      date: "2026-09-09",
      nav: 111.84928206,
      cashPct: 20,
      investedPct: 80,
      dayReturnPct: null,
      source: "finalized_accounting",
      contract: "finalized_accounting",
      seriesSeam: false,
    },
  ];
}

const kpi = (navHistory: NavPoint[]) =>
  computeLivePerformanceKpis({
    positions: [],
    navHistory: navHistory.map((n) => ({ date: n.date, nav: n.nav })),
  });

describe("NAV series seam (#3935)", () => {
  it("flags an explicit series_seam row and a detected source flip", () => {
    expect(isNavSeriesSeam({ seriesSeam: true }, "legacy_nav_history")).toBe(true);
    expect(isNavSeriesSeam({ source: "finalized_accounting" }, "legacy_nav_history")).toBe(true);
    expect(isNavSeriesSeam({ source: "legacy_nav_history" }, "legacy_nav_history")).toBe(false);
    expect(isNavSeriesSeam({ source: "legacy_nav_history" }, null)).toBe(false);
  });

  it("finds the seam date(s)", () => {
    expect(findNavSeriesSeams(seamSeries())).toEqual(["2026-09-08"]);
    expect(findNavSeriesSeams(seamSeries().slice(2))).toEqual([]);
    expect(findNavSeriesSeams([])).toEqual([]);
  });

  it("currentNavRun returns only the current source run, sorted ascending", () => {
    expect(currentNavRun(seamSeries()).map((r) => r.date)).toEqual([
      "2026-09-08",
      "2026-09-09",
    ]);
    // No seam → the whole series, unchanged.
    expect(currentNavRun(seamSeries().slice(2)).map((r) => r.date)).toEqual([
      "2026-09-08",
      "2026-09-09",
    ]);
    expect(currentNavRun([])).toEqual([]);
  });

  it("rebases since-inception on the current run instead of bridging the seam", () => {
    const bridged = kpi(seamSeries());
    // The unbounded series reproduces the defect: the legacy 100 anchor spans
    // the seam to the finalized tip (~+11.8%).
    expect(bridged.sinceInceptionPct).toBeCloseTo((111.84928206 / 100 - 1) * 100, 5);

    const rebased = kpi(currentNavRun(seamSeries()));
    // Fixed: inception is the finalized run's first row, so no phantom jump.
    expect(rebased.sinceInceptionPct).toBeCloseTo(
      (111.84928206 / 110.74928206 - 1) * 100,
      5
    );
    expect(rebased.sinceInceptionStartDate).toBe("2026-09-08");
  });

  it("does not let a seam at the tip produce a session return", () => {
    const tipSeam = seamSeries().slice(1, 3);
    const bridged = kpi(tipSeam);
    expect(bridged.dayReturnPct).toBeCloseTo((110.74928206 / 99.92 - 1) * 100, 5);

    const rebased = kpi(currentNavRun(tipSeam));
    expect(rebased.dayReturnPct).toBe(0);
  });
});
