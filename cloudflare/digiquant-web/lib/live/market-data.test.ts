/**
 * #4013 — the digiquant.io benchmark leg reads the R2-backed market API.
 *
 * `fetchBenchmarkHistory` is the benchmark history's only browser caller of
 * `/v1/market/closes`; `useLivePortfolio` hands off to it when
 * `NEXT_PUBLIC_MARKET_DATA_URL` is set and keeps its Supabase `price_history`
 * read otherwise. Every test stubs `fetch` — no network.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { fetchBenchmarkHistory, isMarketDataConfigured } from "./market-data";

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
    expect(isMarketDataConfigured()).toBe(false);
    expect(await fetchBenchmarkHistory("SPY", "2026-09-01")).toEqual([]);
    expect(networkBlocked).not.toHaveBeenCalled();
  });

  it("treats a whitespace-only base URL as unconfigured", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", "   ");
    expect(isMarketDataConfigured()).toBe(false);
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

describe("useLivePortfolio benchmark wiring", () => {
  const read = (file: string) => {
    const path = join(here, file);
    if (!existsSync(path)) throw new Error(`missing ${path}`);
    return readFileSync(path, "utf8");
  };

  it("reads the market API when configured and keeps Supabase otherwise", () => {
    const src = read("useLivePortfolio.ts");
    expect(src).toContain('from "./market-data"');
    expect(src).toContain("isMarketDataConfigured()");
    expect(src).toContain("fetchBenchmarkHistory(LANDING_BENCHMARK_TICKER, firstDate)");
    expect(src).toContain('.from("price_history")');
  });
});
