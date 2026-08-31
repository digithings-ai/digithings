import { describe, expect, it } from "vitest";
import {
  allocatedPctCurve,
  beatsFlatDcaOos,
  fillDayCounts,
  fillMarkersForChart,
  hasTradeKpis,
  indicatorPanels,
  isDcaIndexEntry,
  isDcaTearsheet,
  isValuationOnlyIndex,
  lastAllocatedPct,
  lastAllocatedPctFromIndex,
} from "./dca";
import { inferKind } from "./strategy-kinds";

describe("inferKind", () => {
  it("maps *_sdca slugs to dca and leaves slappers as long_short", () => {
    expect(inferKind("btc_sdca")).toBe("dca");
    expect(inferKind("eth_sdca")).toBe("dca");
    expect(inferKind("btc_slapper")).toBe("long_short");
    expect(inferKind("btc_sdca", "long_only")).toBe("long_only");
  });
});

describe("hasTradeKpis", () => {
  it("hides tiles when the schema reports null, not when the slug is sdca", () => {
    expect(hasTradeKpis(null, null)).toBe(false);
    expect(hasTradeKpis(0, 0)).toBe(true);
    expect(hasTradeKpis(62.5, 1.4)).toBe(true);
  });
});

describe("isDcaIndexEntry", () => {
  it("prefers vs_lump extras over the slug", () => {
    expect(isDcaIndexEntry({ strategy: "mystery", vs_lump_pct: -12 })).toBe(true);
    expect(isDcaIndexEntry({ strategy: "btc_slapper" })).toBe(false);
    expect(isDcaIndexEntry({ strategy: "btc_sdca" })).toBe(true);
  });
});

describe("isDcaTearsheet", () => {
  it("treats a dca block as authoritative", () => {
    expect(
      isDcaTearsheet({
        strategy: "btc_slapper",
        dca: { vs_lump_pct: 1 } as never,
      }),
    ).toBe(true);
    expect(isDcaTearsheet({ strategy: "btc_slapper" })).toBe(false);
  });
});

describe("allocatedPctCurve", () => {
  it("does not use negative capital_deployed as allocation", () => {
    const allocated = allocatedPctCurve({
      allocated_pct_curve: undefined,
      equity_curve: [{ t: "2025-01-20", v: 84232 }],
      capital_deployed_curve: [{ t: "2025-01-20", v: -504.63549 }],
      initial_capital: 1000,
    } as never);
    expect(allocated[0].v).toBeGreaterThan(0);
    expect(allocated[0].v).toBeLessThan(100);
    expect(allocated[0].v).not.toBeCloseTo(-504.63549);
  });
});

describe("fillMarkersForChart", () => {
  it("marks a reconstructed unit drop as a sell", () => {
    const markers = fillMarkersForChart({
      initial_capital: 1000,
      equity_curve: [
        { t: "2025-01-19", v: 1100 },
        { t: "2025-01-20", v: 1050 },
      ],
      capital_deployed_curve: [
        { t: "2025-01-19", v: 90 },
        { t: "2025-01-20", v: -50 },
      ],
      ohlc_bars: [
        { t: "2025-01-19", o: 100, h: 100, l: 100, c: 100 },
        { t: "2025-01-20", o: 110, h: 110, l: 110, c: 110 },
      ],
    } as never);
    expect(markers.some((m) => m.side === "sell" && m.t.startsWith("2025-01-20"))).toBe(true);
  });
});

describe("indicatorPanels", () => {
  it("labels valuation as power law when reconstructing from the index", () => {
    const panels = indicatorPanels({
      risk_curve: [{ t: "2025-01-01", v: 40 }],
    } as never);
    expect(panels[0].display_name).toBe("power law");
    expect(panels[0].in_index).toBe(true);
    expect(panels.some((p) => p.name === "m2" && !p.in_index)).toBe(true);
  });
});

describe("lastAllocatedPct", () => {
  it("prefers dca.allocated_pct and never prints negative deployed", () => {
    expect(
      lastAllocatedPct({
        dca: { allocated_pct: 12.5, capital_deployed_pct: -505 } as never,
        allocated_pct_curve: [{ t: "2025-01-20", v: 12.5 }],
      } as never),
    ).toBe(12.5);
    expect(
      lastAllocatedPctFromIndex({ allocated_pct: 40, capital_deployed_pct: -10 }),
    ).toBe(40);
    expect(lastAllocatedPctFromIndex({ capital_deployed_pct: -505 })).toBeNull();
  });
});

describe("beatsFlatDcaOos", () => {
  it("treats absent and false as no OOS win", () => {
    expect(beatsFlatDcaOos(undefined)).toBe(false);
    expect(beatsFlatDcaOos(false)).toBe(false);
    expect(beatsFlatDcaOos(true)).toBe(true);
  });
});

describe("isValuationOnlyIndex", () => {
  it("is true when extras are zero or omitted", () => {
    expect(isValuationOnlyIndex(undefined)).toBe(true);
    expect(isValuationOnlyIndex({ valuation: 1, m2: 0, dxy: 0 })).toBe(true);
    expect(isValuationOnlyIndex({ valuation: 1, m2: 0.5 })).toBe(false);
    expect(
      isValuationOnlyIndex({
        valuation: 1,
        m2: 0.5,
        dxy: 0.5,
        rs_eth: 0,
        weekly_rsi: 0,
        weekly_macd: 0,
        sma_band: 0,
      }),
    ).toBe(false);
  });
});

describe("fillDayCounts", () => {
  it("uses fill_* fields, not curve-sign buy_days", () => {
    expect(
      fillDayCounts({
        dca: { buy_days: 400, sell_days: 20, fill_buy_days: 3, fill_sell_days: 1 },
      } as never),
    ).toEqual({ buys: 3, sells: 1 });
  });
});
