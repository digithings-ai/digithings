import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  computeStatus,
  createCryptoFeed,
  equityCell,
  formatChange,
  formatCloseStamp,
  formatLiveStamp,
  formatPrice,
  mergeTapeQuotes,
  parseTick,
  TAPE_SYMBOLS,
  type MarketBarStatus,
  type SocketLike,
} from "./market-bar";

const tickJson = (id: string, price: string, open = "100", time = "2026-09-30T12:00:00.000000Z") =>
  JSON.stringify({ type: "ticker", product_id: id, price, open_24h: open, time });

describe("parseTick", () => {
  it("parses a ticker and derives 24h change", () => {
    const t = parseTick(tickJson("BTC-USD", "110", "100"));
    expect(t?.productId).toBe("BTC-USD");
    expect(t?.price).toBe(110);
    expect(t?.changePct).toBeCloseTo(10);
    expect(t?.time).toBe("2026-09-30T12:00:00.000Z");
  });
  it("rejects non-ticker, unknown product, bad price, bad json", () => {
    expect(parseTick(JSON.stringify({ type: "subscriptions" }))).toBeNull();
    expect(parseTick(tickJson("DOGE-USD", "1"))).toBeNull();
    expect(parseTick(tickJson("BTC-USD", "0"))).toBeNull();
    expect(parseTick(tickJson("BTC-USD", "abc"))).toBeNull();
    expect(parseTick("{nope")).toBeNull();
  });
  it("leaves change null without an open baseline", () => {
    expect(parseTick(tickJson("ETH-USD", "5", "0"))?.changePct).toBeNull();
  });
});

function tupleTickers(src: string, name: string): string[] {
  const marker = `${name}: Final[tuple[str, ...]] = (`;
  const start = src.indexOf(marker);
  const end = src.indexOf("\n)", start);
  return [...src.slice(start + marker.length, end).matchAll(/"([^"]+)"/g)].map((match) => match[1]);
}

describe("baseline tape", () => {
  it("lists every core venue ticker once, skipping Yahoo FX aliases", () => {
    const src = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../../../../digiquant/src/digiquant/data/prices/ticker_venues.py"),
      "utf8",
    );
    const fx = tupleTickers(src, "_FX_TICKERS");
    const expected = [
      ...tupleTickers(src, "_NYSE_TICKERS"),
      ...tupleTickers(src, "_CRYPTO_TICKERS"),
      ...fx.filter((ticker) => !ticker.includes("=")),
    ];
    expect([...TAPE_SYMBOLS]).toEqual(expected);
    expect(TAPE_SYMBOLS).toHaveLength(expected.length);
    for (const alias of fx.filter((ticker) => ticker.includes("="))) {
      expect(TAPE_SYMBOLS).toContain(alias.replace("=X", ""));
      expect(TAPE_SYMBOLS).not.toContain(alias);
    }
  });

  it("keeps a real quote and leaves the rest unavailable", () => {
    const spy = equityCell("SPY", [
      { date: "2026-09-26", price: 100 },
      { date: "2026-09-29", price: 110 },
    ]);
    const close = equityCell("BTC-USD", [
      { date: "2026-09-26", price: 100 },
      { date: "2026-09-29", price: 110 },
    ]);
    expect(spy).not.toBeNull();
    expect(close).not.toBeNull();
    const live = {
      ...close!,
      kind: "crypto" as const,
      price: 120,
      changePct: 1,
      value: "120.00",
      change: "▲1.00%",
      up: true,
    };
    const cells = mergeTapeQuotes([spy!, close!], [live]);
    expect(cells.map((cell) => cell.symbol)).toEqual(["SPY", "BTC-USD"]);
    expect(cells.find((cell) => cell.symbol === "SPY")?.changePct).toBeCloseTo(10);
    expect(cells.find((cell) => cell.symbol === "BTC-USD")?.price).toBe(120);
    expect(cells.find((cell) => cell.symbol === "QQQ")).toBeUndefined();
    const wiped = mergeTapeQuotes([close!], [{ ...live, price: Number.NaN }]);
    expect(wiped.find((cell) => cell.symbol === "BTC-USD")?.price).toBe(110);
  });
});

describe("formatters", () => {
  it("formats price, change and stamp", () => {
    expect(formatPrice(65432.1)).toBe("65,432.10");
    expect(formatPrice(0.5)).toBe("0.5000");
    expect(formatChange(0.4)).toBe("▲0.40%");
    expect(formatChange(-1.234)).toBe("▼1.23%");
    expect(formatChange(null)).toBe("—");
    expect(formatCloseStamp("2026-09-29")).toBe("as of 2026-09-29 close");
    expect(formatLiveStamp("2026-09-30T12:00:00.000Z")).toBe("12:00:00Z");
    expect(formatLiveStamp("2026-09-30T12:00:00.000Z").toLowerCase()).not.toContain("live");
  });
  it("builds an equity cell from the latest close", () => {
    const c = equityCell("SPY", [
      { date: "2026-09-29", price: 110 },
      { date: "2026-09-26", price: 100 },
    ]);
    expect(c?.asOf).toBe("2026-09-29");
    expect(c?.changePct).toBeCloseTo(10);
    expect(equityCell("SPY", [])).toBeNull();
  });
});

describe("computeStatus", () => {
  it("covers the transitions", () => {
    const base = { now: 100_000, failures: 0 };
    expect(computeStatus({ ...base, open: false, lastTickAt: null })).toBe("connecting");
    expect(computeStatus({ ...base, open: false, lastTickAt: null, failures: 3 })).toBe("offline");
    expect(computeStatus({ ...base, open: true, lastTickAt: 90_000 })).toBe("live");
    expect(computeStatus({ ...base, open: true, lastTickAt: 80_000 })).toBe("stale");
    expect(computeStatus({ ...base, open: false, lastTickAt: 95_000 })).toBe("stale");
    expect(computeStatus({ ...base, open: true, lastTickAt: 30_000 })).toBe("offline");
  });
});

class FakeSocket implements SocketLike {
  static all: FakeSocket[] = [];
  onopen: SocketLike["onopen"] = null;
  onmessage: SocketLike["onmessage"] = null;
  onclose: SocketLike["onclose"] = null;
  onerror: SocketLike["onerror"] = null;
  sent: string[] = [];
  closed = false;
  constructor(public url: string) {
    FakeSocket.all.push(this);
  }
  send(d: string) {
    this.sent.push(d);
  }
  close() {
    this.closed = true;
  }
}

describe("createCryptoFeed", () => {
  let statuses: MarketBarStatus[];
  let last: { cells: unknown[]; asOf: string | null } | null;
  const make = () =>
    createCryptoFeed({
      createSocket: (u) => new FakeSocket(u),
      onUpdate: (s) => {
        statuses.push(s.status);
        last = s;
      },
    });

  beforeEach(() => {
    vi.useFakeTimers();
    FakeSocket.all = [];
    statuses = [];
    last = null;
  });
  afterEach(() => vi.useRealTimers());

  it("subscribes on open, goes live on tick, stale then offline without ticks", () => {
    const feed = make();
    feed.start();
    const s = FakeSocket.all[0];
    s.onopen?.();
    expect(JSON.parse(s.sent[0])).toMatchObject({ type: "subscribe", channels: ["ticker"] });
    s.onmessage?.({ data: tickJson("BTC-USD", "110") });
    vi.advanceTimersByTime(500);
    expect(statuses.at(-1)).toBe("live");
    expect(last?.cells).toHaveLength(1);
    vi.advanceTimersByTime(20_000);
    expect(statuses.at(-1)).toBe("stale");
    vi.advanceTimersByTime(60_000);
    expect(statuses.at(-1)).toBe("offline");
    feed.stop();
  });

  it("reconnects with capped exponential backoff and stops on pause/stop", () => {
    const feed = make();
    feed.start();
    FakeSocket.all[0].onclose?.();
    vi.advanceTimersByTime(999);
    expect(FakeSocket.all).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.all).toHaveLength(2);
    FakeSocket.all[1].onclose?.();
    vi.advanceTimersByTime(2_000);
    expect(FakeSocket.all).toHaveLength(3);
    feed.pause();
    expect(FakeSocket.all[2].closed).toBe(true);
    vi.advanceTimersByTime(120_000);
    expect(FakeSocket.all).toHaveLength(3);
    feed.start();
    expect(FakeSocket.all).toHaveLength(4);
    feed.stop();
    expect(FakeSocket.all[3].closed).toBe(true);
  });
});
