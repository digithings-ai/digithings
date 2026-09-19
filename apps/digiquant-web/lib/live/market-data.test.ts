/**
 * #4013/#4053 — digiquant.io reads prices only from the R2-backed market API.
 *
 * `fetchBenchmarkHistory` serves the benchmark leg and `seedFromWorker` the
 * Lane 1 daily-close seed; both call `/v1/market/closes` and return empty when
 * `NEXT_PUBLIC_MARKET_DATA_URL` is unset. There is no Supabase fallback left in
 * `digiquant-web` (#4053): a read of the dropped `price_history` /
 * `public_price_latest` objects would 404, not degrade. Every test stubs
 * `fetch` — no network.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { fetchBenchmarkHistory, seedFromWorker, seedWindowStart } from "./market-data";

const here = dirname(fileURLToPath(import.meta.url));
const MARKET_URL = "https://graph.digithings.ai";

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("fetchBenchmarkHistory", () => {
  it("maps worker rows to {date, price} and passes the window", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", MARKET_URL);
    const urls: string[] = [];
    const fetchMock = vi.fn(async (url: string) => {
      urls.push(url);
      return jsonResponse({
        as_of: "2026-09-11",
        rows: [
          { date: "2026-09-10", ticker: "SPY", close: 660.5 },
          { date: "2026-09-11", ticker: "SPY", close: 662 },
        ],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    expect(await fetchBenchmarkHistory("SPY", "2026-09-01")).toEqual([
      { date: "2026-09-10", price: 660.5 },
      { date: "2026-09-11", price: 662 },
    ]);
    expect(urls[0]).toContain("/v1/market/closes?tickers=SPY&from=2026-09-01");
  });

  it("returns [] when unconfigured and never touches the network", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", "");
    const networkBlocked = vi.fn(async () => {
      throw new Error("network disabled in tests");
    });
    vi.stubGlobal("fetch", networkBlocked);
    expect(await fetchBenchmarkHistory("SPY", "2026-09-01")).toEqual([]);
    expect(networkBlocked).not.toHaveBeenCalled();
  });

  it("treats a whitespace-only base URL as unconfigured", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", "   ");
    expect(await fetchBenchmarkHistory("SPY", "2026-09-01")).toEqual([]);
  });

  it("normalizes a trailing slash on the base URL", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", `${MARKET_URL}/`);
    const urls: string[] = [];
    const fetchMock = vi.fn(async (url: string) => {
      urls.push(url);
      return jsonResponse({ rows: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    await fetchBenchmarkHistory("SPY", "2026-09-01");
    expect(urls[0]).toBe(`${MARKET_URL}/v1/market/closes?tickers=SPY&from=2026-09-01`);
  });

  it("returns [] when the worker rejects the request", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", MARKET_URL);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ error: "bad" }, false, 400)));
    expect(await fetchBenchmarkHistory("SPY", "2026-09-01")).toEqual([]);
    expect(errorSpy).toHaveBeenCalledWith("fetchBenchmarkHistory:", 400);
  });

  it("returns [] on a network failure instead of throwing", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", MARKET_URL);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );
    expect(await fetchBenchmarkHistory("SPY", "2026-09-01")).toEqual([]);
    expect(errorSpy).toHaveBeenCalledWith("fetchBenchmarkHistory:", expect.any(Error));
  });

  it("drops rows that cannot become {date, price} points", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", MARKET_URL);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          rows: [
            { date: "2026-09-10", ticker: "SPY", close: 660.5 },
            { date: "2026-09-11", ticker: "SPY", close: "not-a-number" },
            { ticker: "SPY", close: 661 },
          ],
        }),
      ),
    );
    expect(await fetchBenchmarkHistory("SPY", "2026-09-01")).toEqual([
      { date: "2026-09-10", price: 660.5 },
    ]);
  });
});

describe("seedFromWorker", () => {
  it("seeds live prices from Worker closes", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", MARKET_URL);
    const urls: string[] = [];
    const fetchMock = vi.fn(async (url: string) => {
      urls.push(url);
      return jsonResponse({
        as_of: "2026-09-13",
        rows: [{ date: "2026-09-13", ticker: "AAA", close: 100 }],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const seeds = await seedFromWorker(["AAA"], "2026-09-13");
    expect(seeds).toHaveLength(1);
    expect(seeds[0]).toMatchObject({
      symbol: "AAA",
      price: 100,
      changePct: 0,
      up: true,
      stale: true,
      source: "seed",
    });
    // No `to`: the Worker's default bounds the window at the archive's as_of.
    expect(urls[0]).toBe(`${MARKET_URL}/v1/market/closes?tickers=AAA&from=2026-09-13`);
  });

  it("keeps the latest close per symbol and its prior-session move", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", MARKET_URL);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          // Ascending by (date, ticker), exactly as the Worker sorts.
          rows: [
            { date: "2026-09-10", ticker: "AAA", close: 90 },
            { date: "2026-09-10", ticker: "BBB", close: 50 },
            { date: "2026-09-11", ticker: "AAA", close: 95 },
            { date: "2026-09-11", ticker: "BBB", close: 49 },
          ],
        }),
      ),
    );
    const seeds = await seedFromWorker(["AAA", "BBB"], "2026-09-01");
    expect(seeds).toHaveLength(2);
    const bySymbol = Object.fromEntries(seeds.map((s) => [s.symbol, s]));
    expect(bySymbol.AAA.price).toBe(95);
    expect(bySymbol.AAA.changePct).toBeCloseTo(((95 - 90) / 90) * 100, 6);
    expect(bySymbol.AAA.up).toBe(true);
    expect(bySymbol.BBB.price).toBe(49);
    expect(bySymbol.BBB.changePct).toBeCloseTo(((49 - 50) / 50) * 100, 6);
    expect(bySymbol.BBB.up).toBe(false);
  });

  it("batches requests at the 25-ticker worker cap", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", MARKET_URL);
    const tickers = Array.from({ length: 26 }, (_, i) => `T${i + 1}`);
    const fetchMock = vi.fn(async (url: string) => {
      const asked = new URL(url).searchParams.get("tickers")?.split(",") ?? [];
      return jsonResponse({
        rows: asked.map((ticker) => ({ date: "2026-09-12", ticker, close: 1 })),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const seeds = await seedFromWorker(tickers, "2026-09-01");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const batches = fetchMock.mock.calls.map(
      ([url]) => new URL(String(url)).searchParams.get("tickers")?.split(",") ?? [],
    );
    expect(batches.map((batch) => batch.length)).toEqual([25, 1]);
    expect(batches.flat()).toEqual(tickers);
    expect(seeds).toHaveLength(26);
  });

  it("returns [] when unconfigured and never touches the network", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", "");
    const networkBlocked = vi.fn(async () => {
      throw new Error("network disabled in tests");
    });
    vi.stubGlobal("fetch", networkBlocked);
    expect(await seedFromWorker(["AAA"], "2026-09-01")).toEqual([]);
    expect(networkBlocked).not.toHaveBeenCalled();
  });

  it("returns [] when the worker rejects a batch", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", MARKET_URL);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ error: "bad" }, false, 400)));
    expect(await seedFromWorker(["AAA"], "2026-09-01")).toEqual([]);
    expect(errorSpy).toHaveBeenCalledWith("seedFromWorker:", 400);
  });

  it("returns [] on a network failure instead of throwing", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", MARKET_URL);
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );
    expect(await seedFromWorker(["AAA"], "2026-09-01")).toEqual([]);
    expect(errorSpy).toHaveBeenCalledWith("seedFromWorker:", expect.any(Error));
  });
});

describe("seedWindowStart", () => {
  it("starts the seed window a fixed lookback before now (UTC)", () => {
    // 14 calendar days — enough to hold the last two sessions across a weekend
    // and a holiday, while never reaching past the archive's as_of.
    expect(seedWindowStart(new Date("2026-09-27T12:00:00Z"))).toBe("2026-09-13");
  });
});

describe("digiquant-web market reads are R2-only (#4053)", () => {
  const read = (file: string) => {
    const path = join(here, file);
    if (!existsSync(path)) throw new Error(`missing ${path}`);
    return readFileSync(path, "utf8");
  };

  it("useLivePortfolio reads the benchmark from the market API only", () => {
    const src = read("useLivePortfolio.ts");
    expect(src).toContain('from "./market-data"');
    expect(src).toContain("fetchBenchmarkHistory(LANDING_BENCHMARK_TICKER, firstDate)");
    expect(src).not.toContain("isMarketDataConfigured");
    expect(src).not.toContain("price_history");
  });

  it("useLivePrices seeds Lane 1 from Worker closes", () => {
    const src = read("useLivePrices.ts");
    expect(src).toContain("seedFromWorker");
    expect(src).not.toContain("public_price_latest");
  });

  it("the market client has no dropped-table reads or config gate", () => {
    const src = read("market-data.ts");
    expect(src).not.toContain("isMarketDataConfigured");
    expect(src).not.toContain("price_history");
    expect(src).not.toContain("public_price_latest");
  });
});
