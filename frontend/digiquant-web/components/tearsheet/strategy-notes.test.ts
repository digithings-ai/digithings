import { describe, expect, it } from "vitest";
import { isSlapperStrategy, theoryCopy } from "./strategy-notes";
import { strategyDisplayName } from "./strategy-names";

describe("strategyDisplayName", () => {
  it("uses asset-then-type names even if the store still says Strat or Slapper", () => {
    expect(strategyDisplayName("btc_sdca", "BTC Strategic DCA")).toBe("BTC-SDCA");
    expect(strategyDisplayName("btc_sdca", "BTC SDCA Strat")).toBe("BTC-SDCA");
    expect(strategyDisplayName("btc_sdca", "BTC power-law remaining-book")).toBe("BTC-SDCA");
    expect(strategyDisplayName("btc_slapper", "BTC Slapper")).toBe("BTC L/S");
    expect(strategyDisplayName("eth_slapper", "ETH long/short")).toBe("ETH L/S");
    expect(strategyDisplayName("sol_slapper")).toBe("SOL L/S");
  });
});

describe("strategy notes", () => {
  it("still treats slappers as slapper copy", () => {
    expect(isSlapperStrategy("btc_slapper")).toBe(true);
    expect(isSlapperStrategy("btc_sdca")).toBe(false);
    expect(theoryCopy("BTC", "btc_slapper")[0]).toMatch(/Mean-reversion/);
  });

  it("renders remaining-book notes instead of dropping SDCA", () => {
    const lines = theoryCopy("BTC", "btc_sdca");
    expect(lines.length).toBeGreaterThan(0);
    expect(lines.join(" ")).toMatch(/BTC-SDCA/);
    expect(lines.join(" ")).not.toMatch(/SDCA Strat/i);
    expect(lines.join(" ")).toMatch(/composite valuation index/i);
    expect(lines.join(" ")).not.toMatch(/power law \+ M2 \+ DXY/i);
    expect(lines.join(" ")).toMatch(/remaining cash/i);
    expect(lines.join(" ")).toMatch(/not a live strategy/i);
    expect(lines.join(" ")).toMatch(/Buy-and-hold is the public benchmark/i);
    expect(lines.join(" ")).not.toMatch(/beat the market/i);
    expect(lines.join(" ")).not.toMatch(/power-law remaining-book/i);
    expect(lines.join(" ")).not.toMatch(/not a multi-indicator composite/i);
    expect(lines.join(" ")).not.toMatch(/curve_simulator/i);
    expect(lines.join(" ")).not.toMatch(/btc_stage1/i);
  });
});
