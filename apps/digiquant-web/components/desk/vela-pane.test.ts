import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  HOUSE_PROVIDER_NAME,
  HouseBarsProvider,
  fetchHouseBars,
  houseBarsFromResponse,
  houseSymbol,
  houseTimeframe,
} from "./house-bars-provider";
import { VELA_SYMBOL, VELA_TIMEFRAME, VELA_UNAVAILABLE, velaWorkspaceOptions } from "./vela-options";

/**
 * The defect this pins: the desk registered Vela's browser-side Binance and
 * Coinbase providers, so `/tools/charts` rendered `binance:BTCUSDT` and fetched it
 * from api.binance.com / fapi.binance.com (CORS, and not house data). Every
 * assertion here is about the vendor path being gone.
 */
describe("LuxAlgo Vela workspace", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("mounts one dark chart on house bars, not a vendor feed", () => {
    const options = velaWorkspaceOptions();
    expect(VELA_UNAVAILABLE).toBe("LuxAlgo Vela · chart unavailable");
    expect(HOUSE_PROVIDER_NAME).toBe("house");
    expect(VELA_SYMBOL).toBe("house:BTC-USD");
    expect(houseSymbol(VELA_SYMBOL.split(":")[1])).toBe("house:BTC-USD");
    expect(VELA_TIMEFRAME).toBe("15");
    expect(options.layout).toBe(false);
    expect(options.symbol).toBe("house:BTC-USD");
    expect(options.timeframe).toBe("15");
    expect(options.theme).toBe("dark");
    expect(Object.keys(options.providers ?? {})).toEqual(["house"]);
    expect(options.animations).toBeUndefined();
    expect(options.watermark).toBeUndefined();
    expect("autoscale" in options).toBe(false);
  });

  it("registers no vendor provider anywhere in the desk chrome or the FX hero", () => {
    const read = (p: string) => readFileSync(new URL(p, import.meta.url), "utf8");
    const pane = read("./vela-pane.tsx");
    const options = read("./vela-options.ts");
    const hero = read("../../app/_chrome/QuantField.tsx");
    for (const [name, src] of [["vela-pane", pane], ["vela-options", options], ["QuantField", hero]] as const) {
      expect(src, `${name} still names a vendor provider`).not.toMatch(/luxalgo\/vela\/providers\//);
      expect(src, `${name} still names Binance`).not.toMatch(/BinanceProvider|binance:/i);
      expect(src, `${name} still names Coinbase`).not.toMatch(/CoinbaseProvider|coinbase:/i);
    }
    expect(pane).toContain('import("@luxalgo/vela/workspace")');
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

  it("maps Vela timeframes onto the ones digiquant serves, and refuses the rest", () => {
    expect(houseTimeframe("1")).toBe("1m");
    expect(houseTimeframe("15")).toBe("15m");
    expect(houseTimeframe("60")).toBe("1h");
    expect(houseTimeframe("D")).toBe("1d");
    expect(houseTimeframe("W")).toBe("1wk");
    expect(houseTimeframe("M")).toBe("1mo");
    expect(houseTimeframe("3")).toBeNull();
    expect(houseTimeframe("")).toBeNull();
  });

  it("drops rows it cannot plot rather than plotting them wrong", () => {
    const bars = houseBarsFromResponse({
      bars: [
        { timestamp: "2026-10-01T00:00:00Z", open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
        { timestamp: "not-a-date", open: 1, high: 2, low: 0.5, close: 1.5 },
        { timestamp: "2026-10-02T00:00:00Z", open: 1, high: null, low: 0.5, close: 1.5 },
      ],
    });
    expect(bars).toHaveLength(1);
    expect(bars[0]).toEqual({ time: Date.parse("2026-10-01T00:00:00Z"), open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 });
    expect(houseBarsFromResponse({ bars: "nope" })).toEqual([]);
    expect(houseBarsFromResponse(null)).toEqual([]);
  });

  it("reads the keyless digiquant route and stays empty when unconfigured", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_BASE_URL", "");
    expect(await fetchHouseBars("BTC-USD", "15")).toEqual([]);

    const calls: string[] = [];
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_BASE_URL", "https://quant.example.test/");
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      calls.push(url);
      return {
        ok: true,
        json: async () => ({ bars: [{ timestamp: "2026-10-01T00:00:00Z", open: 1, high: 2, low: 0.5, close: 1.5 }] }),
      };
    }));
    const bars = await fetchHouseBars("BTC-USD", "15");
    expect(calls).toEqual(["https://quant.example.test/bars?symbol=BTC-USD&timeframe=15m&limit=300"]);
    expect(bars).toHaveLength(1);

    // A timeframe digiquant does not serve is never sent, so no silent 400.
    expect(await fetchHouseBars("BTC-USD", "3")).toEqual([]);
    expect(calls).toHaveLength(1);
  });

  it("a failed read is empty, never a vendor fallback", async () => {
    vi.stubEnv("NEXT_PUBLIC_DIGIQUANT_BASE_URL", "https://quant.example.test");
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 502, json: async () => ({}) })));
    expect(await fetchHouseBars("BTC-USD", "D")).toEqual([]);
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    expect(await fetchHouseBars("BTC-USD", "D")).toEqual([]);
  });

  it("advertises itself as keyless history, never a streaming feed", async () => {
    const info = new HouseBarsProvider().info();
    expect(info.name).toBe("house");
    expect(info.requiresApiKey).toBe(false);
    expect(info.capabilities).toEqual({ enumerate: true, stream: false, symbolInfo: true });
    expect(await new HouseBarsProvider().listSymbols()).toEqual([]);
  });
});
