import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { VELA_PRODUCTS, VELA_UNAVAILABLE, velaChartOptions, velaHostStyle } from "./vela-options";

describe("LuxAlgo Vela charts", () => {
  it("holds opacity at 0, fades over 700ms, and shows reduced motion immediately", () => {
    expect(velaHostStyle(false, false)).toEqual({ opacity: "0", transition: "opacity 700ms ease" });
    expect(velaHostStyle(false, true)).toEqual({ opacity: "1", transition: "opacity 700ms ease" });
    expect(velaHostStyle(true, false)).toEqual({ opacity: "1", transition: "none" });
  });

  it("uses Coinbase for BTC, ETH, and SOL only, with autoscale off", () => {
    expect(VELA_PRODUCTS).toEqual(["BTC-USD", "ETH-USD", "SOL-USD"]);
    expect(VELA_UNAVAILABLE).toBe("LuxAlgo Vela · chart unavailable");
    const options = velaChartOptions("ETH-USD", false);
    expect(options.symbol).toBe("coinbase:ETH-USD");
    expect(options.animations).toMatchObject({ autoscale: false });
    expect(velaChartOptions("SOL-USD", true).animations).toBe(false);
  });

  it("does not draw an SVG axis or a second exchange", () => {
    const src = readFileSync(new URL("./vela-pane.tsx", import.meta.url), "utf8");
    expect(src).not.toMatch(/<svg/i);
    expect(src).toContain("autoScale: false");
    expect(src).toContain("CoinbaseProvider");
    expect(src).not.toContain("binance");
    expect(src).not.toContain("SPY");
    expect(src).toContain("VELA_UNAVAILABLE");
  });
});
