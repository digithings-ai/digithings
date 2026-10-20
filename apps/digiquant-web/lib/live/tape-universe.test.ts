import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  canonicalTapeSymbol,
  loadTapeUniverse,
  mergeTapeUniverse,
  portfolioTickersFrom,
  TAPE_SYMBOLS,
} from "./tape-universe";

const MARKET_URL = "https://graph.digithings.ai";
const API_URL = `${MARKET_URL}/dashboard-api`;

const json = (body: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

/** Route the two reads the loader makes; every other URL is a bug, not a fallback. */
function stubFeeds(market: { body?: unknown; status?: number } | null, portfolio: { body?: unknown; status?: number } | null) {
  const seen: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      seen.push(url);
      if (url.startsWith(`${MARKET_URL}/v1/market/`)) {
        if (!market) return json({ error: "unconfigured" }, 404);
        return json(market.body ?? {}, market.status ?? 200);
      }
      if (url.startsWith(`${API_URL}/portfolio`)) {
        if (!portfolio) return json({ error: "not_found" }, 404);
        return json(portfolio.body ?? {}, portfolio.status ?? 200);
      }
      throw new Error(`unstubbed URL ${url}`);
    }),
  );
  return seen;
}

const held = ["UUP", "XLV", "XLF", "GLD", "EWZ", "DBO"];
const portfolioBody = {
  data: {
    positions: held.map((ticker) => ({ ticker, weight_pct: 1, scaled_weight_pct: 1, is_cash: false })),
  },
};
const marketBody = { as_of: "2026-10-10", tickers: ["AGG", "BTC-USD", "COPX", "SPY", "TLT"] };

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", MARKET_URL);
  vi.stubEnv("NEXT_PUBLIC_DASHBOARD_API_URL", API_URL);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("canonicalTapeSymbol", () => {
  it("folds a Yahoo =X alias onto its base and trims", () => {
    expect(canonicalTapeSymbol("EURUSD=X")).toBe("EURUSD");
    expect(canonicalTapeSymbol("  spy ")).toBe("SPY");
    expect(canonicalTapeSymbol("btc-usd")).toBe("BTC-USD");
  });
  it("rejects nothing that names an asset", () => {
    expect(canonicalTapeSymbol("")).toBeNull();
    expect(canonicalTapeSymbol("   ")).toBeNull();
    expect(canonicalTapeSymbol("=X")).toBeNull();
  });
});

describe("mergeTapeUniverse", () => {
  // The acceptance test: the tape covers every symbol in the price tables.
  it("covers every price-table symbol", () => {
    const universe = mergeTapeUniverse(held, marketBody.tickers);
    for (const ticker of marketBody.tickers) expect(universe).toContain(ticker);
    expect(new Set(universe).size).toBe(universe.length);
  });

  it("covers a held symbol the price tables do not carry", () => {
    const universe = mergeTapeUniverse(["VTWO", "ZZZZ"], marketBody.tickers);
    expect(universe).toContain("VTWO");
    expect(universe).toContain("ZZZZ");
  });

  it("is the union, not an intersection or a concatenation", () => {
    const universe = mergeTapeUniverse(["SPY", "VTWO"], ["SPY", "TLT"]);
    expect(universe).toEqual(["SPY", "VTWO", "TLT"]);
  });

  it("normalises case, whitespace and =X aliases, once each", () => {
    const universe = mergeTapeUniverse([" spy ", "EURUSD=X"], ["SPY", "eurusd", "  EURUSD  "]);
    expect(universe).toEqual(["SPY", "EURUSD"]);
  });

  it("invents nothing from two empty reads", () => {
    expect(mergeTapeUniverse([], [])).toEqual([]);
    expect(mergeTapeUniverse(["  ", "=X"], [])).toEqual([]);
  });

  it("never yields a non-string the caller handed it", () => {
    const junk = [null, 42, {}] as unknown as string[];
    expect(mergeTapeUniverse(junk, marketBody.tickers)).toEqual(marketBody.tickers);
  });
});

describe("portfolioTickersFrom", () => {
  it("reads the house book positions", () => {
    expect(portfolioTickersFrom(portfolioBody)).toEqual(held);
  });

  it("is empty on every other shape, so a bad read is never a phantom book", () => {
    for (const body of [null, {}, { data: null }, { data: {} }, { data: { positions: {} } }, { data: { positions: [{}, { n: 1 }] } }]) {
      expect(portfolioTickersFrom(body)).toEqual([]);
    }
  });
});

describe("loadTapeUniverse", () => {
  it("unions the live holdings with the live price tables", async () => {
    const seen = stubFeeds({ body: marketBody }, { body: portfolioBody });
    const universe = await loadTapeUniverse();
    expect(seen).toEqual([`${MARKET_URL}/v1/market/tickers`, `${API_URL}/portfolio`]);
    for (const ticker of marketBody.tickers) expect(universe).toContain(ticker);
    for (const ticker of held) expect(universe).toContain(ticker);
    expect(new Set(universe).size).toBe(universe.length);
  });

  it("still covers the price tables when the portfolio read is withheld", async () => {
    stubFeeds({ body: marketBody }, { body: { error: { message: "upstream_empty" } }, status: 502 });
    const universe = await loadTapeUniverse();
    for (const ticker of marketBody.tickers) expect(universe).toContain(ticker);
  });

  it("fills the baseline tape when the market worker is unconfigured", async () => {
    stubFeeds(null, { body: portfolioBody });
    const universe = await loadTapeUniverse();
    for (const ticker of held) expect(universe).toContain(ticker);
    expect(universe).toContain("BTC-USD");
    expect(universe).toContain("SPY");
    expect(new Set(universe).size).toBe(universe.length);
  });

  // An unset NEXT_PUBLIC_MARKET_DATA_URL ships commented out, so the degraded
  // path is reachable in a real build and must not blank the ticker.
  it("falls back to the baseline snapshot only when both reads are empty", async () => {
    stubFeeds(null, null);
    expect(await loadTapeUniverse()).toEqual([...TAPE_SYMBOLS]);
  });
});
