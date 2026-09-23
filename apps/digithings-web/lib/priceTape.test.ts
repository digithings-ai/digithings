import { describe, expect, it } from "vitest";
import {
  fmtTapeChange,
  fmtTapePrice,
  seedWindowStart,
  tapeRowsToItems,
  type MarketCloseRow,
} from "./priceTape";

/**
 * The tape's folding and formatting are the only parts of the live banner that
 * can be checked without a network, so they carry the test weight. The hook's
 * behaviour (empty until the read lands) follows from these and is covered in the
 * browser pass.
 */

describe("priceTape formatting", () => {
  it("scales decimals to magnitude", () => {
    expect(fmtTapePrice(63410)).toBe("63,410");
    expect(fmtTapePrice(548.21)).toBe("548.21");
    expect(fmtTapePrice(1)).toBe("1.00");
    expect(fmtTapePrice(0.4213)).toBe("0.4213");
    expect(fmtTapePrice(Number.NaN)).toBe("—");
  });

  it("prints change as an unsigned percentage", () => {
    expect(fmtTapeChange(-2.1)).toBe("2.10%");
    expect(fmtTapeChange(1.235)).toBe("1.24%");
    expect(fmtTapeChange(Number.NaN)).toBe("0.00%");
  });
});

describe("priceTape window", () => {
  it("starts the lookback in the past", () => {
    const now = new Date("2026-09-23T12:00:00Z");
    expect(seedWindowStart(now)).toBe("2026-09-09");
  });
});

describe("tapeRowsToItems", () => {
  const rows: MarketCloseRow[] = [
    { date: "2026-09-10", ticker: "btc-usd", close: 62000 },
    { date: "2026-09-11", ticker: "BTC-USD", close: 63410 },
    { date: "2026-09-11", ticker: "SPY", close: 548.21 },
    { date: "2026-09-10", ticker: "SPY", close: 550 },
  ];

  it("takes the latest close against the one before it, per ticker", () => {
    const items = tapeRowsToItems(rows);
    const btc = items.find((item) => item.symbol === "BTC-USD");
    const spy = items.find((item) => item.symbol === "SPY");
    expect(btc).toEqual({ symbol: "BTC-USD", last: "63,410", change: "2.27%", up: true });
    expect(spy).toEqual({ symbol: "SPY", last: "548.21", change: "0.33%", up: false });
  });

  it("does not fabricate a change from a single session", () => {
    const items = tapeRowsToItems([{ date: "2026-09-11", ticker: "GLD", close: 241.5 }]);
    expect(items).toEqual([{ symbol: "GLD", last: "241.50", change: "0.00%", up: true }]);
  });

  it("drops blank and non-numeric rows instead of rendering NaN", () => {
    const items = tapeRowsToItems([
      { date: "2026-09-11", ticker: "  ", close: 10 },
      { date: "2026-09-11", ticker: "BAD", close: Number.NaN },
      { date: "2026-09-11", ticker: "OK", close: 12 },
    ]);
    expect(items.map((item) => item.symbol)).toEqual(["OK"]);
  });

  it("orders rows by date rather than trusting payload order", () => {
    const items = tapeRowsToItems([
      { date: "2026-09-11", ticker: "ETH-USD", close: 3000 },
      { date: "2026-09-10", ticker: "ETH-USD", close: 2900 },
    ]);
    expect(items[0].last).toBe("3,000");
    expect(items[0].up).toBe(true);
  });
});
