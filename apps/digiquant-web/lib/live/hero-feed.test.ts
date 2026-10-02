import { describe, expect, it } from "vitest";
import { applyTick, type FeedCandle } from "./hero-feed";

const candle = (t: number, o: number, c: number): FeedCandle => ({ t, o, h: Math.max(o, c), l: Math.min(o, c), c });

describe("applyTick", () => {
  it("moves the forming candle inside its minute", () => {
    const candles = [candle(60, 100, 101)];
    applyTick(candles, 103, 90);
    applyTick(candles, 99, 110);
    expect(candles).toHaveLength(1);
    expect(candles[0]).toMatchObject({ t: 60, o: 100, h: 103, l: 99, c: 99 });
  });

  it("opens the next minute at the previous close", () => {
    const candles = [candle(60, 100, 101)];
    applyTick(candles, 104, 125);
    expect(candles).toHaveLength(2);
    expect(candles[1]).toMatchObject({ t: 120, o: 101, h: 104, l: 101, c: 104 });
  });

  it("starts a series from the first tick", () => {
    const candles: FeedCandle[] = [];
    applyTick(candles, 50, 61);
    expect(candles).toEqual([{ t: 60, o: 50, h: 50, l: 50, c: 50 }]);
  });
});
