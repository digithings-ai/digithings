import { afterEach, describe, expect, it, vi } from "vitest";
import {
  AdminNotConfiguredError,
  createPostgrestPricesLive,
  supabaseBase,
} from "./admin";

// The route tests never reach this file (they inject a stub), so without
// these tests the PostgREST layer would be green by construction no matter
// how wrong it is. Every test below drives the REAL implementation against a
// stubbed `fetch` and asserts on the recorded request or the returned shape.

const ENV = {
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "service-role-key",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("supabaseBase", () => {
  it("throws when the service key is missing", () => {
    expect(() => supabaseBase({ SUPABASE_URL: "https://x" })).toThrow(AdminNotConfiguredError);
  });

  it("honours the CORE_ fallback chain", () => {
    const base = supabaseBase({
      CORE_SUPABASE_URL: "https://core.supabase.co/",
      CORE_SUPABASE_SERVICE_KEY: "k",
    });
    expect(base.url).toBe("https://core.supabase.co");
  });
});

describe("claimRefresh", () => {
  it("wins only on data === true", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(true)));
    const db = createPostgrestPricesLive(ENV);
    await expect(db.claimRefresh(50)).resolves.toBe(true);
    const calls = (fetch as unknown as { mock: { calls: Array<[unknown, unknown]> } }).mock.calls;
    const [url, init] = calls[0] as [string, RequestInit];
    expect(url).toContain("rpc/claim_prices_live_refresh");
    expect(init.method).toBe("POST");
  });

  it("fails closed on false, null, and RPC errors", async () => {
    for (const body of [false, null, 1, "true"]) {
      vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(body)));
      await expect(createPostgrestPricesLive(ENV).claimRefresh(50)).resolves.toBe(false);
    }
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ code: "PGRST202", message: "missing" }, 404)));
    await expect(createPostgrestPricesLive(ENV).claimRefresh(50)).resolves.toBe(false);
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new Error("transport down");
    }));
    await expect(createPostgrestPricesLive(ENV).claimRefresh(50)).resolves.toBe(false);
  });
});

describe("listPortfolioTickers", () => {
  it("returns raw tickers; the handler owns CASH/dedupe", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse([{ ticker: "AAPL" }, { ticker: "CASH" }])),
    );
    await expect(createPostgrestPricesLive(ENV).listPortfolioTickers()).resolves.toEqual([
      "AAPL",
      "CASH",
    ]);
  });

  it("returns null when the view hiccups", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ message: "nope" }, 500)));
    await expect(createPostgrestPricesLive(ENV).listPortfolioTickers()).resolves.toBeNull();
  });
});

describe("upsertPrices", () => {
  it("resolves to DO UPDATE, never ignore-duplicates", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await createPostgrestPricesLive(ENV).upsertPrices([
      {
        ticker: "SPY",
        price: 1,
        change: null,
        change_pct: null,
        quoted_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]);
    expect(result).toBe("ok");
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit]>;
    const [url, init] = calls[0] as [string, RequestInit];
    expect(url).toContain("on_conflict=ticker");
    const prefer = (init.headers as Record<string, string>).Prefer;
    expect(prefer).toContain("resolution=merge-duplicates");
    expect(prefer).not.toContain("ignore-duplicates");
  });

  it("carries the error message verbatim", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ code: "PGRST205", message: "table missing" }, 400)),
    );
    await expect(createPostgrestPricesLive(ENV).upsertPrices([])).resolves.toBe("table missing");
  });
});
