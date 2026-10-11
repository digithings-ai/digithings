import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { DataProvider } from "@luxalgo/vela/providers/binance";
import { VELA_SYMBOL, VELA_TIMEFRAME, VELA_UNAVAILABLE, velaWorkspaceOptions } from "./vela-options";

class StubProvider {}

describe("LuxAlgo Vela workspace", () => {
  it("mounts one dark chart on Binance BTCUSDT at 15 minutes", () => {
    const options = velaWorkspaceOptions(
      StubProvider as new () => DataProvider,
      StubProvider as new () => DataProvider,
    );
    expect(VELA_UNAVAILABLE).toBe("LuxAlgo Vela · chart unavailable");
    expect(VELA_SYMBOL).toBe("binance:BTCUSDT");
    expect(VELA_TIMEFRAME).toBe("15");
    expect(options.layout).toBe(false);
    expect(options.symbol).toBe("binance:BTCUSDT");
    expect(options.timeframe).toBe("15");
    expect(options.theme).toBe("dark");
    expect(Object.keys(options.providers ?? {})).toEqual(["binance", "coinbase"]);
    expect(options.animations).toBeUndefined();
    expect(options.watermark).toBeUndefined();
    expect("autoscale" in options).toBe(false);
  });

  it("uses the workspace, not a custom symbol bar or a locked price window", () => {
    const pane = readFileSync(new URL("./vela-pane.tsx", import.meta.url), "utf8");
    const options = readFileSync(new URL("./vela-options.ts", import.meta.url), "utf8");
    expect(pane).toContain('import("@luxalgo/vela/workspace")');
    expect(pane).toContain("BinanceProvider");
    expect(pane).toContain("CoinbaseProvider");
    expect(pane).toContain("VELA_UNAVAILABLE");
    expect(pane).not.toMatch(/<svg/i);
    expect(pane).not.toContain("lockPriceFrame");
    expect(pane).not.toContain("addNativeIndicator");
    expect(pane).not.toContain("autoScale");
    expect(pane).not.toContain("vela-pinets");
    expect(pane).not.toContain("SPY");
    expect(pane).not.toContain("@digithings/ui");
    expect(options).not.toContain("autoscale: false");
    expect(options).not.toMatch(/watermark:\s*false/);
    expect(pane).not.toMatch(/attribution/);
    expect(options).toContain('theme: "dark"');
    expect(options).toContain("layout: false");
  });
});
