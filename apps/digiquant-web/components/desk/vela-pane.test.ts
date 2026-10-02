import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { HeroBar } from "@/lib/hero-build";
import { coinbaseBars, lockedPriceWindow } from "./vela-scale";
import { VELA_PRODUCTS, VELA_UNAVAILABLE, velaChartOptions, velaHostStyle, velaReadyCaption } from "./vela-options";

function seriesAround(price: number): HeroBar[] {
  const out: HeroBar[] = [];
  for (let i = 0; i < 60; i++) {
    const close = price + Math.sin(i / 4) * price * 0.01;
    out.push({
      time: 1_700_000_000_000 + i * 60_000,
      open: close - 1,
      high: close + price * 0.002,
      low: close - price * 0.002,
      close,
      volume: 12 + i,
    });
  }
  return out;
}

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
    expect(options.volume).toBe(true);
    expect(options.animations).toMatchObject({ autoscale: false });
    expect(velaChartOptions("SOL-USD", true).animations).toBe(false);
    expect(velaReadyCaption("BTC-USD")).toBe("LuxAlgo Vela · BTC-USD · 1m · volume · SMA 20 · EMA 50 · Bollinger");
  });

  it("locks the price window to the series, not the empty 0–1 scale", () => {
    const btc = lockedPriceWindow(seriesAround(64_000));
    const eth = lockedPriceWindow(seriesAround(3_200));
    const sol = lockedPriceWindow(seriesAround(180));
    expect(btc.min).toBeGreaterThan(50_000);
    expect(btc.max).toBeLessThan(80_000);
    expect(eth.min).toBeGreaterThan(2_000);
    expect(eth.max).toBeLessThan(5_000);
    expect(sol.min).toBeGreaterThan(100);
    expect(sol.max).toBeLessThan(300);
    expect(coinbaseBars([{ time: 1, open: 2, high: 3, low: 1, close: 2 }])).toHaveLength(1);
    expect(coinbaseBars([{ close: 1 }])).toEqual([]);
  });

  it("does not draw an SVG axis or a second exchange", () => {
    const pane = readFileSync(new URL("./vela-pane.tsx", import.meta.url), "utf8");
    const scale = readFileSync(new URL("./vela-scale.ts", import.meta.url), "utf8");
    expect(pane).not.toMatch(/<svg/i);
    expect(scale).toContain("autoScale: false");
    expect(scale).toContain('addNativeIndicator("sma"');
    expect(scale).toContain('addNativeIndicator("ema"');
    expect(scale).toContain('addNativeIndicator("bollinger-bands"');
    expect(pane).toContain("CoinbaseProvider");
    expect(pane).not.toContain("binance");
    expect(pane).not.toContain("SPY");
    expect(pane).toContain("VELA_UNAVAILABLE");
    expect(pane).toContain("lockPriceFrame");
  });
});
