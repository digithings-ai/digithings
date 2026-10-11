import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import { TAPE_SYMBOLS } from "./tape-universe";
import {
  barsFromCoinbase,
  barsFromMarketRows,
  heroWatermark,
  marketLookback,
  nextHero,
  type HeroSeries,
} from "./hero-series";

describe("hero series", () => {
  it("reads the tape universe instead of a second symbol list", () => {
    const src = readFileSync(new URL("./hero-series.ts", import.meta.url), "utf8");
    expect(src).toContain('from "./tape-universe"');
    expect(src).not.toContain("HERO_PRODUCTS");
    expect(src).not.toContain("CRYPTO_PRODUCTS");
    expect(TAPE_SYMBOLS).toContain("SPY");
    expect(TAPE_SYMBOLS).toContain("GLD");
    expect(TAPE_SYMBOLS).toContain("EURUSD");
    expect(TAPE_SYMBOLS).toContain("BTC-USD");
  });

  it("maps Coinbase minute tuples and drops a row that is not a candle", () => {
    const bars = barsFromCoinbase([
      [120, 9, 12, 10, 11, 4],
      [60, 8, 11, 9, 10, 3],
      [180, 1, 0, 1, 1, 1],
      "nope",
    ]);
    expect(bars.map((bar) => bar.time)).toEqual([60_000, 120_000]);
    expect(bars[0]).toMatchObject({ open: 9, high: 11, low: 8, close: 10, volume: 3 });
  });

  it("does not turn a close-only market row into a candle", () => {
    expect(
      barsFromMarketRows([
        { date: "2026-09-10", close: 100 },
        { date: "2026-09-11", close: 101 },
      ]),
    ).toEqual([]);
  });

  it("keeps daily OHLC from the market archive", () => {
    const bars = barsFromMarketRows([
      { date: "2026-09-11", open: 102, high: 106, low: 101, close: 104, volume: 9 },
      { date: "2026-09-10", open: 100, high: 103, low: 99, close: 102, volume: 8 },
    ]);
    expect(bars).toHaveLength(2);
    expect(bars[0].time).toBe(Date.parse("2026-09-10T00:00:00.000Z"));
    expect(bars[1]).toMatchObject({ open: 102, high: 106, low: 101, close: 104 });
  });

  it("skips a symbol with no candles and returns the next one that has them", async () => {
    const symbols = ["SPY", "GLD", "BTC-USD"];
    const load = vi.fn(async (symbol: string): Promise<HeroSeries | null> => {
      if (symbol !== "GLD") return null;
      return {
        symbol,
        timeframe: "1D",
        velaTimeframe: "D",
        source: "market",
        bars: [
          { time: 1, open: 1, high: 2, low: 1, close: 2 },
          { time: 2, open: 2, high: 3, low: 2, close: 3 },
        ],
      };
    });
    const found = await nextHero(0, load, undefined, symbols);
    expect(found?.index).toBe(1);
    expect(found?.series.symbol).toBe("GLD");
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("names the asset and the timeframe on one line", () => {
    expect(heroWatermark("BTC-USD", "1m")).toBe("BTC · 1m");
    expect(heroWatermark("EURUSD", "1D")).toBe("EURUSD · 1D");
  });

  it("asks the archive for a short daily window", () => {
    expect(marketLookback(new Date("2026-10-03T00:00:00.000Z"))).toBe("2026-03-17");
  });
});
