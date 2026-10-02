import { describe, expect, it } from "vitest";
import {
  benchmarkFromBenchmarks,
  cardFromPerformance,
  classifyOfficialRead,
  isStubPayload,
  officialApiBase,
  portfolioFromPerformance,
  strategiesFromCatalog,
} from "./officialBand";

describe("official band reads", () => {
  it("uses the dev proxy on loopback and the production API otherwise", () => {
    expect(officialApiBase("127.0.0.1")).toBe("/official-api");
    expect(officialApiBase("digithings.ai")).toBe("https://graph.digithings.ai/dashboard-api");
  });

  it("withholds stub envelopes and unpublished reads", () => {
    expect(isStubPayload({ provenance: { contract: "legacy_estimate" } })).toBe(true);
    expect(classifyOfficialRead(200, { data: { nav: 99.909 } }).ok).toBe(false);
    expect(classifyOfficialRead(403, { error: { code: "forbidden" } }).ok).toBe(false);
    expect(classifyOfficialRead(200, { data: { nav: { points: [] } } }).ok).toBe(true);
  });

  it("maps a performance index and a benchmark leg", () => {
    expect(
      portfolioFromPerformance({
        data: { nav: { points: [{ date: "2026-01-02", index: 101.5 }, { date: "2026-01-03", index: 0 }] } },
      }),
    ).toEqual([{ date: "2026-01-02", nav: 101.5 }]);
    expect(
      benchmarkFromBenchmarks(
        { data: { series: { SPY: [{ date: "2026-01-03", close: 510 }, { date: "2026-01-02", close: 500 }] } } },
        "SPY",
      ),
    ).toEqual([
      { date: "2026-01-02", price: 500 },
      { date: "2026-01-03", price: 510 },
    ]);
  });

  it("maps catalog rows and tearsheet cards without filling missing figures", () => {
    expect(
      strategiesFromCatalog({
        data: { strategies: [{ id: "btc_slapper", name: "BTC L/S", universe: "BTC" }, { name: "nope" }] },
      }),
    ).toEqual([{ id: "btc_slapper", name: "BTC L/S", symbol: "BTC" }]);
    expect(
      cardFromPerformance({
        data: { card: { id: "btc_slapper", name: "BTC L/S", net_profit_pct: 12.5, win_rate_pct: null } },
      }),
    ).toMatchObject({ id: "btc_slapper", netProfitPct: 12.5, winRatePct: null, maxDrawdownPct: null });
    expect(cardFromPerformance({ data: { available: false } })).toBeNull();
  });
});
