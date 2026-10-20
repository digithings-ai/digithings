/**
 * DIG-2857 — the tear-sheet data mapping.
 *
 * `fetchTearsheet` / `fetchStrategyIndex` read `strategy_tearsheets` through
 * the official API table route. While the worker refused that table every read
 * came back `not_found`, both helpers returned their empty value, and every
 * card on digiquant.io rendered honest-empty instead of its statistics. These
 * tests pin the other side of that door: a published row maps into POPULATED
 * statistics, and the empty value is reached only for a genuinely absent read.
 *
 * Every test stubs `fetch` — no network.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchStrategyIndex, fetchTearsheet } from "./strategies";

/** One row as the official API serves it: the tearsheet payload under `metrics`. */
function apiRow(strategy: string, overrides: Record<string, unknown> = {}) {
  return {
    strategy_id: strategy,
    metrics: {
      schema_version: "1.3",
      strategy,
      symbol: "BTC-USD",
      engine: "slapper",
      generated_at: "2026-10-10T22:00:00Z",
      data_source: "backtest",
      period_start: "2021-01-01",
      period_end: "2026-10-09",
      bars: 1421,
      initial_capital: 10000,
      final_equity: 31250.5,
      net_profit: 21250.5,
      net_profit_pct: 212.5,
      max_drawdown_pct: -18.4,
      sharpe_ratio: 1.42,
      sortino_ratio: 2.1,
      calmar_ratio: 1.15,
      profit_factor: 1.63,
      win_rate_pct: 54.2,
      total_trades: 96,
      avg_trade: 221.36,
      overall: {
        trades: 96,
        net_profit: 21250.5,
        net_profit_pct: 212.5,
        gross_profit: 33120.9,
        gross_loss: -11870.4,
        percent_profitable: 54.2,
        profit_factor: 1.63,
        avg_trade: 221.36,
        wins: 52,
        losses: 44,
      },
      long: null,
      short: null,
      equity_curve: [],
      drawdown_curve: [],
      trades: [],
      notes: [],
      label: "BTC L/S",
      kind: "long_short",
      ...overrides,
    },
  };
}

function stubFetch(status: number, body: unknown) {
  const urls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
      };
    }),
  );
  return urls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("fetchTearsheet", () => {
  it("maps a published row to populated statistics", async () => {
    const urls = stubFetch(200, [apiRow("btc_slapper")]);

    const data = await fetchTearsheet("btc_slapper");

    expect(data).not.toBeNull();
    // The three numbers the tear sheets were missing.
    expect(data!.net_profit_pct).toBe(212.5);
    expect(data!.sharpe_ratio).toBe(1.42);
    expect(data!.max_drawdown_pct).toBe(-18.4);
    expect(data!.profit_factor).toBe(1.63);
    expect(data!.win_rate_pct).toBe(54.2);
    expect(data!.total_trades).toBe(96);
    expect(data!.generated_at).toBe("2026-10-10T22:00:00Z");
    // It reads the table route, filtered to the one strategy.
    expect(urls).toHaveLength(1);
    expect(urls[0]).toContain("/v1/tables/strategy_tearsheets");
    expect(urls[0]).toContain("eq.strategy_id=btc_slapper");
    expect(urls[0]).toContain("limit=1");
  });

  it("returns null when the API withheld the table", async () => {
    stubFetch(404, { error: { code: "not_found", message: "table … is not served" } });
    expect(await fetchTearsheet("btc_slapper")).toBeNull();
  });

  it("returns null when the strategy has no published row", async () => {
    stubFetch(200, []);
    expect(await fetchTearsheet("btc_slapper")).toBeNull();
  });

  it("returns null when the row carries no metrics payload", async () => {
    stubFetch(200, [{ strategy_id: "btc_slapper", metrics: null }]);
    expect(await fetchTearsheet("btc_slapper")).toBeNull();
  });
});

describe("fetchStrategyIndex", () => {
  it("projects each published row into a populated index card", async () => {
    stubFetch(200, [
      apiRow("btc_slapper"),
      apiRow("btc_sdca", {
        label: "BTC-SDCA",
        kind: "dca",
        net_profit_pct: 88.1,
        sharpe_ratio: null,
        dca: { vs_lump_pct: 12.4, capital_deployed_pct: 61.5, allocated_pct: 73.2 },
      }),
    ]);

    const cards = await fetchStrategyIndex();

    expect(cards).toHaveLength(2);
    expect(cards[0]).toMatchObject({
      strategy: "btc_slapper",
      label: "BTC L/S",
      kind: "long_short",
      symbol: "BTC-USD",
      net_profit_pct: 212.5,
      max_drawdown_pct: -18.4,
      profit_factor: 1.63,
      win_rate_pct: 54.2,
      total_trades: 96,
      href: "/strategies/btc_slapper",
    });
    // DCA extras are read off the nested block when present, else off the
    // flattened index extras the pipeline writes beside it.
    expect(cards[1].vs_lump_pct).toBe(12.4);
    expect(cards[1].capital_deployed_pct).toBe(61.5);
    expect(cards[1].allocated_pct).toBe(73.2);
    // An absent index extra stays null rather than becoming 0.
    expect(cards[0].avg_trade_pct).toBeNull();
  });

  it("returns [] when the API withheld the table", async () => {
    stubFetch(502, { error: { code: "upstream_empty" } });
    expect(await fetchStrategyIndex()).toEqual([]);
  });

  it("skips a row without a metrics payload instead of rendering an empty card", async () => {
    stubFetch(200, [{ strategy_id: "btc_slapper", metrics: {} }, apiRow("eth_slapper")]);
    const cards = await fetchStrategyIndex();
    expect(cards.map((c) => c.strategy)).toEqual(["eth_slapper"]);
  });
});