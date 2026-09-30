import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  computeStatus,
  createCryptoFeed,
  equityCell,
  formatChange,
  formatCloseStamp,
  formatPrice,
  parseTick,
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

describe("formatters", () => {
  it("formats price, change and stamp", () => {
    expect(formatPrice(65432.1)).toBe("65,432.10");
    expect(formatPrice(0.5)).toBe("0.5000");
    expect(formatChange(0.4)).toBe("▲0.40%");
    expect(formatChange(-1.234)).toBe("▼1.23%");
    expect(formatChange(null)).toBe("—");
    expect(formatCloseStamp("2026-09-29")).toBe("as of 2026-09-29 close");
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
