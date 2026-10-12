import { describe, expect, it } from "vitest";
import { bookModel, drawdownFromNav, EM, figPlainPct, figPx, figSignedPct } from "./terminal-book";
import type { LivePosition } from "@/lib/live/types";

const empty = {
  loading: false,
  configured: false,
  error: null,
  navContractError: null,
  positions: [] as LivePosition[],
  nav: [],
  metricsAsOf: null,
  kpis: null,
};

describe("terminal book figures", () => {
  it("renders an em dash for a missing figure and never a stand-in zero", () => {
    expect(figSignedPct(null)).toBe(EM);
    expect(figSignedPct(undefined)).toBe(EM);
    expect(figPlainPct(Number.NaN)).toBe(EM);
    expect(figPx(null)).toBe(EM);
    expect(figSignedPct(1.2)).toBe("+1.20%");
    expect(figSignedPct(-0.5)).toBe("-0.50%");
    expect(figSignedPct(0)).toBe("0.00%");
  });

  it("withholds every figure when the house book is not connected", () => {
    const model = bookModel(empty);
    expect(model.connected).toBe(false);
    expect(model.reason).toContain("not connected");
    expect(model.kpis.map((k) => k.value)).toEqual([EM, EM, EM, EM]);
    expect(model.holdings).toEqual([]);
    expect(model.navPoints).toEqual([]);
    expect(model.drawdown.maxPct).toBeNull();
  });

  it("shows a real weight and an em dash where the mark is missing", () => {
    const position: LivePosition = {
      ticker: "SPY",
      name: null,
      category: "Equity",
      sectorBucket: null,
      weightPct: 12.5,
      entryPrice: null,
      entryDate: null,
      currentPrice: null,
      dayChangePct: null,
      unrealizedPnlPct: null,
      sinceEntryReturnPct: null,
      metricsAsOf: "2026-09-01",
      livePrice: null,
      isLive: false,
    };
    const model = bookModel({
      ...empty,
      configured: true,
      positions: [position],
      metricsAsOf: "2026-09-01",
    });
    expect(model.holdings[0]?.weight).toBe("12.50%");
    expect(model.holdings[0]?.mark).toBe(EM);
    expect(model.holdings[0]?.name).toBe(EM);
    expect(model.holdings[0]?.shares).toBe(EM);
    expect(model.holdings[0]?.day).toBe(EM);
    expect(model.movers).toEqual([]);
    expect(model.sleeves[0]).toEqual({ sleeve: "Equity", names: "1", weight: "12.50%" });
    expect(model.kpis[0]?.value).toBe(EM);
    expect(model.kpis[3]?.value).toBe("1");
  });

  it("computes drawdown only from the NAV points it is given", () => {
    expect(drawdownFromNav([])).toEqual({
      maxPct: null,
      currentPct: null,
      peakDate: null,
      troughDate: null,
    });
    const read = drawdownFromNav([
      { date: "2026-01-01", nav: 100 },
      { date: "2026-01-02", nav: 120 },
      { date: "2026-01-03", nav: 90 },
    ]);
    expect(read.maxPct).toBeCloseTo(-25);
    expect(read.currentPct).toBeCloseTo(-25);
    expect(read.peakDate).toBe("2026-01-02");
    expect(read.troughDate).toBe("2026-01-03");
    expect(drawdownFromNav([
      { date: "2026-01-01", nav: 100 },
      { date: "2026-01-02", nav: 110 },
    ]).maxPct).toBe(0);
  });
});
