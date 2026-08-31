import { describe, expect, it } from "vitest";
import {
  inferKind,
  inferPublicType,
  matchesPublicType,
  publicTypeFilterOptions,
  publicTypeLabel,
} from "./strategy-kinds";
import { filterLibrary } from "./strategy-library";
import { type StrategyIndexEntry } from "./types";

function stub(partial: Partial<StrategyIndexEntry> & Pick<StrategyIndexEntry, "strategy">): StrategyIndexEntry {
  return {
    symbol: "BTC-USD",
    engine: "nautilus",
    period_start: "2018-01-01",
    period_end: "2026-01-01",
    net_profit_pct: 10,
    max_drawdown_pct: -20,
    profit_factor: 1.5,
    win_rate_pct: 50,
    avg_trade_pct: 1,
    total_trades: 10,
    generated_at: "2026-01-01T00:00:00Z",
    href: `/strategies/${partial.strategy}`,
    ...partial,
  };
}

describe("inferKind", () => {
  it("maps *_sdca slugs to dca and leaves slappers as long_short", () => {
    expect(inferKind("btc_sdca")).toBe("dca");
    expect(inferKind("eth_sdca")).toBe("dca");
    expect(inferKind("btc_slapper")).toBe("long_short");
    expect(inferKind("btc_sdca", "long_only")).toBe("long_only");
  });
});

describe("public strategy type", () => {
  it("maps catalog slugs to SDCA vs L/S and reserves RS", () => {
    expect(inferPublicType("btc_sdca")).toBe("sdca");
    expect(inferPublicType("btc_sdca", "dca")).toBe("sdca");
    expect(inferPublicType("btc_slapper")).toBe("long_short");
    expect(inferPublicType("eth_slapper", "long_short")).toBe("long_short");
    expect(inferPublicType("sol_slapper")).toBe("long_short");
    expect(inferPublicType("btc_rs", "relative_strength")).toBe("relative_strength");
    expect(publicTypeLabel("sdca")).toBe("SDCA");
    expect(publicTypeLabel("long_short")).toBe("L/S");
    expect(publicTypeLabel("relative_strength")).toBe("RS");
    expect(publicTypeLabel("mystery")).toBe("mystery");
  });

  it("filters All | SDCA | L/S from the enum and keeps unknown types on All", () => {
    const labels = publicTypeFilterOptions().map((o) => o.label);
    expect(labels).toEqual(["All", "SDCA", "L/S"]);
    expect(matchesPublicType("btc_sdca", "dca", "all")).toBe(true);
    expect(matchesPublicType("btc_sdca", "dca", "sdca")).toBe(true);
    expect(matchesPublicType("btc_sdca", "dca", "long_short")).toBe(false);
    expect(matchesPublicType("btc_slapper", "long_short", "long_short")).toBe(true);
    expect(matchesPublicType("btc_slapper", "long_short", "sdca")).toBe(false);
    expect(matchesPublicType("future_book", "custom", "all")).toBe(true);
    expect(matchesPublicType("future_book", "custom", "sdca")).toBe(false);
  });

  it("filters the existing library list without inventing a second catalog", () => {
    const catalog = [
      stub({ strategy: "btc_slapper", kind: "long_short", net_profit_pct: 40 }),
      stub({ strategy: "eth_slapper", kind: "long_short", net_profit_pct: 20 }),
      stub({ strategy: "sol_slapper", kind: "long_short", net_profit_pct: 10 }),
      stub({ strategy: "btc_sdca", kind: "dca", net_profit_pct: 5 }),
    ];
    expect(filterLibrary(catalog, "all", "cagr").map((e) => e.strategy)).toEqual([
      "btc_slapper",
      "eth_slapper",
      "sol_slapper",
      "btc_sdca",
    ]);
    expect(filterLibrary(catalog, "sdca", "cagr").map((e) => e.strategy)).toEqual(["btc_sdca"]);
    expect(filterLibrary(catalog, "long_short", "cagr").map((e) => e.strategy)).toEqual([
      "btc_slapper",
      "eth_slapper",
      "sol_slapper",
    ]);
    expect(filterLibrary(catalog, "relative_strength", "cagr")).toEqual([]);
  });
});
