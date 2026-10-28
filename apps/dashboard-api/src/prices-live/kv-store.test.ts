import { describe, expect, it, vi } from "vitest";
import {
  createKvPricesLive,
  KvNotBoundError,
  LEASE_KEY,
  pricesLiveBackend,
  QUOTES_KEY,
  readQuotes,
  type PricesLiveKv,
} from "./kv-store";
import type { PriceRow } from "./market";
import { createPricesLiveFetch } from "./router";
import { handlePricesLive } from "./routes";

// Supabase exit S4: prices-live on Workers KV behind PRICES_LIVE_BACKEND.
// In-memory KV only. No network: the Finnhub fetch is injected.

function memoryKv(seed: Record<string, string> = {}): PricesLiveKv & {
  store: Map<string, string>;
  puts: Array<{ key: string; ttl?: number }>;
} {
  const store = new Map(Object.entries(seed));
  const puts: Array<{ key: string; ttl?: number }> = [];
  return {
    store,
    puts,
    async get(key) {
      return store.get(key) ?? null;
    },
    async put(key, value, options) {
      puts.push({ key, ttl: options?.expirationTtl });
      store.set(key, value);
    },
  };
}

const T0 = new Date("2026-08-03T14:00:00.000Z"); // Monday, market open

function row(ticker: string, price: number, at = T0): PriceRow {
  return {
    ticker,
    price,
    change: 1,
    change_pct: 0.5,
    quoted_at: at.toISOString(),
    updated_at: at.toISOString(),
  };
}

describe("pricesLiveBackend", () => {
  it("defaults to supabase and picks kv only on the exact value", () => {
    expect(pricesLiveBackend(undefined)).toBe("supabase");
    expect(pricesLiveBackend({})).toBe("supabase");
    expect(pricesLiveBackend({ PRICES_LIVE_BACKEND: "KV" })).toBe("supabase");
    expect(pricesLiveBackend({ PRICES_LIVE_BACKEND: " kv " })).toBe("kv");
  });
});

describe("createKvPricesLive", () => {
  it("throws KvNotBoundError without the binding", () => {
    expect(() => createKvPricesLive({})).toThrow(KvNotBoundError);
  });

  it("claims an empty window, then refuses inside it, then claims after it", async () => {
    const kv = memoryKv();
    let now = T0;
    const db = createKvPricesLive({ PRICES_LIVE_KV: kv }, () => now);
    expect(await db.claimRefresh(55)).toBe(true);
    expect(kv.store.get(LEASE_KEY)).toBe(T0.toISOString());
    expect(kv.puts[0].ttl).toBeGreaterThanOrEqual(60);
    now = new Date(T0.getTime() + 30_000);
    expect(await db.claimRefresh(55)).toBe(false);
    now = new Date(T0.getTime() + 56_000);
    expect(await db.claimRefresh(55)).toBe(true);
  });

  it("fails closed on an unparseable lease stamp and on a KV error", async () => {
    const bad = createKvPricesLive({ PRICES_LIVE_KV: memoryKv({ [LEASE_KEY]: "garbage" }) });
    expect(await bad.claimRefresh(55)).toBe(false);
    const throwing: PricesLiveKv = {
      get: vi.fn(async () => {
        throw new Error("kv down");
      }),
      put: vi.fn(async () => undefined),
    };
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(await createKvPricesLive({ PRICES_LIVE_KV: throwing }).claimRefresh(55)).toBe(false);
    errSpy.mockRestore();
  });

  it("merges upserts by ticker and keeps the latest updated_at", async () => {
    const kv = memoryKv();
    const db = createKvPricesLive({ PRICES_LIVE_KV: kv });
    expect(await db.upsertPrices([row("AAPL", 1), row("MSFT", 2)])).toBe("ok");
    const later = new Date(T0.getTime() + 60_000);
    expect(await db.upsertPrices([row("AAPL", 3, later)])).toBe("ok");
    const snap = await readQuotes(kv);
    expect(snap.updated_at).toBe(later.toISOString());
    expect(Object.keys(snap.rows).sort()).toEqual(["AAPL", "MSFT"]);
    expect(snap.rows.AAPL.price).toBe(3);
    expect(snap.rows.MSFT.price).toBe(2);
  });

  it("reads a corrupt snapshot as empty instead of throwing", async () => {
    expect(await readQuotes(memoryKv({ [QUOTES_KEY]: "{not json" }))).toEqual({
      updated_at: null,
      rows: {},
    });
  });

  it("takes tickers from PRICES_LIVE_TICKERS without touching Supabase", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const db = createKvPricesLive({
      PRICES_LIVE_KV: memoryKv(),
      PRICES_LIVE_TICKERS: " AAPL, ,msft ",
      SUPABASE_URL: "https://core.example",
      SUPABASE_SERVICE_ROLE_KEY: "k",
    });
    expect(await db.listPortfolioTickers()).toEqual(["AAPL", "msft"]);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("returns no tickers (majors only) when neither the list nor Supabase is set", async () => {
    const db = createKvPricesLive({ PRICES_LIVE_KV: memoryKv() });
    expect(await db.listPortfolioTickers()).toEqual([]);
  });
});

describe("handlePricesLive on the kv backend", () => {
  const ENV = { FINNHUB_API_KEY: "test-finnhub-key", PRICES_LIVE_BACKEND: "kv" };
  const quote = async () => ({ c: 10, d: 1, dp: 0.1, t: 1785765600 });

  function post(): Request {
    return new Request("https://worker/prices-live", { method: "POST", body: "{}" });
  }

  it("publishes to KV with no Supabase env at all", async () => {
    const kv = memoryKv();
    const res = await handlePricesLive(
      post(),
      { ...ENV, PRICES_LIVE_KV: kv },
      {
        fetchQuoteFn: quote,
        now: () => new Date(T0),
        sleep: async () => undefined,
      },
    );
    const body = (await res.json()) as Record<string, unknown>;
    expect(body).toMatchObject({ market: "open", published: "ok" });
    const snap = await readQuotes(kv);
    expect(Object.keys(snap.rows).length).toBe(body.quoted);
    expect(snap.updated_at).toBe(T0.toISOString());
  });

  it("500s when the flag is on and the binding is missing", async () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const res = await handlePricesLive(post(), ENV, {
      fetchQuoteFn: quote,
      now: () => new Date(T0),
      sleep: async () => undefined,
    });
    errSpy.mockRestore();
    expect(res.status).toBe(500);
    expect(await res.json()).toEqual({ error: "prices-live kv not bound" });
  });
});

describe("router: cron bearer and the quotes read", () => {
  const deps = {
    fetchQuoteFn: async () => ({ c: 10, d: 1, dp: 0.1, t: 1785765600 }),
    now: () => new Date(T0),
    sleep: async () => undefined,
  };

  it("refuses POST /prices-live without the cron token, and when none is configured", async () => {
    const kv = memoryKv();
    const env = { FINNHUB_API_KEY: "k", PRICES_LIVE_BACKEND: "kv", PRICES_LIVE_KV: kv };
    const noToken = createPricesLiveFetch(env, deps);
    const res = await noToken.fetch(
      new Request("https://w/prices-live", {
        method: "POST",
        headers: { Authorization: "Bearer anything" },
      }),
    );
    expect(res.status).toBe(401);
    const withToken = createPricesLiveFetch({ ...env, PRICES_LIVE_CRON_TOKEN: "secret-a" }, deps);
    for (const auth of [undefined, "Bearer secret-b", "Bearer secret-a-longer", "secret-a"]) {
      const headers: Record<string, string> = auth ? { Authorization: auth } : {};
      const r = await withToken.fetch(
        new Request("https://w/prices-live", { method: "POST", headers }),
      );
      expect(r.status, String(auth)).toBe(401);
    }
    expect(kv.puts).toEqual([]);
  });

  it("runs the refresh with the right token and serves the snapshot", async () => {
    const kv = memoryKv();
    const env = {
      FINNHUB_API_KEY: "k",
      PRICES_LIVE_BACKEND: "kv",
      PRICES_LIVE_KV: kv,
      PRICES_LIVE_CRON_TOKEN: "secret-a",
    };
    const app = createPricesLiveFetch(env, deps);
    const res = await app.fetch(
      new Request("https://w/prices-live", {
        method: "POST",
        headers: { Authorization: "Bearer secret-a" },
        body: "{}",
      }),
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ published: "ok" });
    const quotes = await app.fetch(new Request("https://w/prices-live/quotes"));
    expect(quotes.status).toBe(200);
    const snap = (await quotes.json()) as { updated_at: string; rows: Record<string, unknown> };
    expect(snap.updated_at).toBe(T0.toISOString());
    expect(Object.keys(snap.rows).length).toBeGreaterThan(0);
  });

  it("answers 404 for the quotes read on the supabase backend, 405 for a GET refresh", async () => {
    const app = createPricesLiveFetch({ PRICES_LIVE_KV: memoryKv() }, deps);
    expect((await app.fetch(new Request("https://w/prices-live/quotes"))).status).toBe(404);
    expect((await app.fetch(new Request("https://w/prices-live"))).status).toBe(405);
  });
});
