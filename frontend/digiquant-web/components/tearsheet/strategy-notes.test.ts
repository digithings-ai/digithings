import { describe, expect, it } from "vitest";
import { isSlapperStrategy, theoryCopy } from "./strategy-notes";
import { strategyDisplayName } from "./strategy-names";

describe("strategyDisplayName", () => {
  it("uses the canonical remaining-book name even if the store still says Strategic DCA", () => {
    expect(strategyDisplayName("btc_sdca", "BTC Strategic DCA")).toBe(
      "BTC power-law remaining-book",
    );
    expect(strategyDisplayName("btc_slapper", "BTC Slapper")).toBe("BTC long/short");
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
    expect(lines.join(" ")).toMatch(/power-law remaining-book/i);
    expect(lines.join(" ")).toMatch(/not a multi-indicator composite/i);
    expect(lines.join(" ")).toMatch(/does not beat flat DCA/i);
    expect(lines.join(" ")).toMatch(/not a live trading strategy/i);
    expect(lines.join(" ")).not.toMatch(/beat the market/i);
    expect(lines.join(" ")).not.toMatch(/curve_simulator/i);
    expect(lines.join(" ")).not.toMatch(/btc_stage1/i);
  });
});
