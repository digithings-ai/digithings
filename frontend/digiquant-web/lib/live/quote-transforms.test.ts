import { describe, expect, it } from "vitest";
import type { LivePriceMap, LiveQuote } from "./types";
import { positionRowToLive } from "./quote-transforms";

function seed(symbol: string, price: number, changePct: number): LiveQuote {
  return {
    symbol,
    price,
    changePct,
    up: changePct >= 0,
    ts: 1,
    stale: true,
    source: "seed",
  };
}

function liveTick(symbol: string, price: number, changePct: number): LiveQuote {
  return { ...seed(symbol, price, changePct), stale: false, source: "postgres_changes" };
}

const unmarkedVgk = {
  ticker: "VGK",
  name: "Vanguard FTSE Europe",
  category: "etf",
  sector_bucket: "international",
  weight_pct: 24.8479,
  entry_price: 90.99,
  entry_date: "2026-08-20",
  current_price: null,
  day_change_pct: null,
  unrealized_pnl_pct: null,
  since_entry_return_pct: null,
  metrics_as_of: null,
};

describe("positionRowToLive — public_price_latest seed fallback (#3447)", () => {
  it("uses a stale seed close for mark / day / since-entry when the book has no current_price", () => {
    const quotes: LivePriceMap = { VGK: seed("VGK", 90.9, 0.2) };
    const pos = positionRowToLive(unmarkedVgk, quotes);
    expect(pos.currentPrice).toBe(90.9);
    expect(pos.livePrice).toBe(90.9);
    expect(pos.isLive).toBe(false);
    expect(pos.dayChangePct).toBe(0.2);
    expect(pos.sinceEntryReturnPct).not.toBeNull();
    expect(pos.sinceEntryReturnPct!).toBeCloseTo(((90.9 - 90.99) / 90.99) * 100, 6);
  });

  it("lets a live tick win the display price without losing the seed as the mark", () => {
    const quotes: LivePriceMap = { VGK: liveTick("VGK", 91.1, 0.35) };
    const pos = positionRowToLive(unmarkedVgk, quotes);
    expect(pos.isLive).toBe(true);
    expect(pos.livePrice).toBe(91.1);
    expect(pos.currentPrice).toBe(91.1);
    expect(pos.dayChangePct).toBe(0.35);
  });

  it("keeps stored snapshot marks when the book already has current_price", () => {
    const quotes: LivePriceMap = { VGK: seed("VGK", 90.9, 0.2) };
    const pos = positionRowToLive(
      {
        ...unmarkedVgk,
        current_price: 90.72,
        day_change_pct: -1.03,
        since_entry_return_pct: -0.3,
        metrics_as_of: "2026-09-01",
      },
      quotes,
    );
    expect(pos.currentPrice).toBe(90.72);
    expect(pos.livePrice).toBe(90.72);
    expect(pos.dayChangePct).toBe(-1.03);
    expect(pos.sinceEntryReturnPct).toBe(-0.3);
    expect(pos.metricsAsOf).toBe("2026-09-01");
    expect(pos.isLive).toBe(false);
  });

  it("fail-closes to null prices when the book is unmarked and no quote exists", () => {
    const pos = positionRowToLive(unmarkedVgk, {});
    expect(pos.currentPrice).toBeNull();
    expect(pos.livePrice).toBeNull();
    expect(pos.dayChangePct).toBeNull();
    expect(pos.sinceEntryReturnPct).toBeNull();
    expect(pos.isLive).toBe(false);
  });

  it("leaves CASH priceless even if a stray quote is in the map", () => {
    const pos = positionRowToLive(
      { ticker: "CASH", weight_pct: 15.8, current_price: null },
      { CASH: seed("CASH", 1, 0) },
    );
    expect(pos.ticker).toBe("CASH");
    expect(pos.currentPrice).toBeNull();
    expect(pos.livePrice).toBeNull();
    expect(pos.isLive).toBe(false);
  });
});
