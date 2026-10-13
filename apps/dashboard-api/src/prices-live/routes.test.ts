import { describe, expect, it, vi } from "vitest";
import { handlePricesLive, type PricesLiveDeps } from "./routes";
import type { PricesLiveDb } from "./admin";
import type { PricesLiveEnv } from "./env";
import { MAX_SYMBOLS } from "./market";
import type { QuoteOut } from "./market";

// Contract parity for the Workers port of the prices-live edge function.
//
// Every expectation below is a body shape copied from the edge handler the
// port replaces: `{ dormant }`, `{ market: "closed" }`,
// `{ skipped: "not claimed" }`, `{ error: "supabase environment not
// configured" }`, and the open-market report. The port's whole contract is
// "same wire shape", so the assertions are on the exact bodies, never on
// `res.ok`.

const MON_OPEN = new Date("2026-08-03T14:00:00.000Z"); // Monday, hour 14 UTC
const WED_CLOSED = new Date("2026-08-05T10:00:00.000Z"); // Wednesday, hour 10 UTC

const FULL_ENV: PricesLiveEnv = {
  FINNHUB_API_KEY: "test-finnhub-key",
  SUPABASE_URL: "https://core.supabase.co",
  SUPABASE_SERVICE_ROLE_KEY: "service-role-key",
};

const QUOTE: QuoteOut = { c: 100, d: 1, dp: 0.5, t: 1722600000 };

function dbStub(overrides: Partial<PricesLiveDb> = {}): PricesLiveDb & {
  claimRefresh: ReturnType<typeof vi.fn>;
  listPortfolioTickers: ReturnType<typeof vi.fn>;
  upsertPrices: ReturnType<typeof vi.fn>;
} {
  return {
    claimRefresh: vi.fn(async () => true),
    listPortfolioTickers: vi.fn(async () => []),
    upsertPrices: vi.fn(async () => "ok"),
    ...overrides,
  } as PricesLiveDb & {
    claimRefresh: ReturnType<typeof vi.fn>;
    listPortfolioTickers: ReturnType<typeof vi.fn>;
    upsertPrices: ReturnType<typeof vi.fn>;
  };
}

function deps(
  db: PricesLiveDb = dbStub(),
  extra: Partial<PricesLiveDeps> = {},
): PricesLiveDeps {
  return {
    admin: db,
    fetchQuoteFn: async () => ({ ...QUOTE }),
    now: () => new Date(MON_OPEN),
    sleep: async () => undefined,
    ...extra,
  };
}

function post(body: unknown): Request {
  return new Request("https://worker/prices-live", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("prices-live wire contract", () => {
  it("answers dormant when the Finnhub key is unset", async () => {
    const res = await handlePricesLive(post({}), {}, deps());
    expect(res.status).toBe(200);
    const body = (await res.json()) as Record<string, unknown>;
    expect(body.dormant).toBe(true);
    expect(typeof body.at).toBe("string");
  });

  it("answers market closed outside extended US hours", async () => {
    const db = dbStub();
    const res = await handlePricesLive(
      post({}),
      FULL_ENV,
      deps(db, { now: () => new Date(WED_CLOSED) }),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as Record<string, unknown>;
    expect(body).toMatchObject({ market: "closed" });
    expect(db.claimRefresh).not.toHaveBeenCalled();
  });

  it("force overrides the market gate but never the claim", async () => {
    const db = dbStub({
      claimRefresh: vi.fn(async () => false),
    });
    const res = await handlePricesLive(
      post({ force: true }),
      FULL_ENV,
      deps(db, { now: () => new Date(WED_CLOSED) }),
    );
    const body = (await res.json()) as Record<string, unknown>;
    expect(body).toMatchObject({ skipped: "not claimed" });
    expect(db.claimRefresh).toHaveBeenCalledTimes(1);
  });

  it("force:true reaches the open-market report when the claim wins", async () => {
    const res = await handlePricesLive(
      post({ force: true }),
      FULL_ENV,
      deps(dbStub(), { now: () => new Date(WED_CLOSED) }),
    );
    const body = (await res.json()) as Record<string, unknown>;
    expect(body).toMatchObject({ market: "open", forced: true, published: "ok" });
  });

  it("treats a malformed JSON body as force:false", async () => {
    const req = new Request("https://worker/prices-live", { method: "POST", body: "not json" });
    const res = await handlePricesLive(req, FULL_ENV, deps());
    const body = (await res.json()) as Record<string, unknown>;
    expect(body).toMatchObject({ market: "open", forced: false });
  });

  it("500s with the edge body when Supabase env is missing", async () => {
    const res = await handlePricesLive(post({}), { FINNHUB_API_KEY: "k" }, {
      fetchQuoteFn: async () => ({ ...QUOTE }),
      now: () => new Date(MON_OPEN),
      sleep: async () => undefined,
    });
    expect(res.status).toBe(500);
    expect(await res.json()).toEqual({ error: "supabase environment not configured" });
  });

  it("skips without fetching when the claim loses", async () => {
    const fetchQuoteFn = vi.fn(async () => ({ ...QUOTE }));
    const db = dbStub({ claimRefresh: vi.fn(async () => false) });
    const res = await handlePricesLive(post({}), FULL_ENV, deps(db, { fetchQuoteFn }));
    expect(await res.json()).toMatchObject({ skipped: "not claimed" });
    expect(fetchQuoteFn).not.toHaveBeenCalled();
    expect(db.listPortfolioTickers).not.toHaveBeenCalled();
    expect(db.upsertPrices).not.toHaveBeenCalled();
  });

  it("merges majors with portfolio tickers, drops CASH, dedupes", async () => {
    const db = dbStub({
      listPortfolioTickers: vi.fn(async () => ["AAPL", "CASH", " aapl ", "MSFT"]),
    });
    const seen: string[] = [];
    const res = await handlePricesLive(
      post({}),
      FULL_ENV,
      deps(db, {
        fetchQuoteFn: async (symbol) => {
          seen.push(symbol);
          return { ...QUOTE };
        },
      }),
    );
    const body = (await res.json()) as Record<string, unknown>;
    expect(body.published).toBe("ok");
    // 10 majors + AAPL + MSFT = 12 distinct; CASH excluded, aapl deduped.
    expect(body.symbols).toBe(12);
    expect(body.quoted).toBe(12);
    expect(seen).not.toContain("CASH");
    expect(seen.filter((s) => s === "AAPL")).toHaveLength(1);
    // Upsert rows carry the wire column names and ISO timestamps.
    const upsertArg = db.upsertPrices.mock.calls[0]![0] as Array<Record<string, unknown>>;
    const aapl = upsertArg.find((r) => r.ticker === "AAPL")!;
    expect(aapl.price).toBe(100);
    expect(aapl.change).toBe(1);
    expect(aapl.change_pct).toBe(0.5);
    expect(aapl.quoted_at).toBe(new Date(1722600000 * 1000).toISOString());
    expect(typeof aapl.updated_at).toBe("string");
  });

  it("degrades to majors-only when the ticker view hiccups", async () => {
    const db = dbStub({ listPortfolioTickers: vi.fn(async () => null) });
    const res = await handlePricesLive(post({}), FULL_ENV, deps(db));
    const body = (await res.json()) as Record<string, unknown>;
    expect(body).toMatchObject({ market: "open", symbols: 10, quoted: 10, published: "ok" });
  });

  it("carries the upsert error verbatim and still answers 200", async () => {
    const db = dbStub({ upsertPrices: vi.fn(async () => "PGRST205 table missing") });
    const res = await handlePricesLive(post({}), FULL_ENV, deps(db));
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ published: "PGRST205 table missing" });
  });

  it("reports skipped (no quotes) when every fetch fails", async () => {
    const db = dbStub();
    const res = await handlePricesLive(
      post({}),
      FULL_ENV,
      deps(db, {
        fetchQuoteFn: async (symbol) => {
          throw new Error(`Finnhub HTTP 429 for ${symbol}`);
        },
      }),
    );
    const body = (await res.json()) as Record<string, unknown>;
    expect(body).toMatchObject({ published: "skipped (no quotes)", quoted: 0 });
    expect(body.failed).toBe((body.symbols as number) ?? 0);
    expect(db.upsertPrices).not.toHaveBeenCalled();
  });

  it("truncates to the symbol cap, never more", async () => {
    const many = Array.from({ length: MAX_SYMBOLS + 10 }, (_, i) => `T${i}`);
    const db = dbStub({ listPortfolioTickers: vi.fn(async () => many) });
    const res = await handlePricesLive(post({}), FULL_ENV, deps(db));
    const body = (await res.json()) as Record<string, unknown>;
    expect(body.symbols).toBe(MAX_SYMBOLS);
  });

  it("falls back to the run clock on a bad Finnhub timestamp", async () => {
    const db = dbStub();
    await handlePricesLive(
      post({}),
      FULL_ENV,
      deps(db, { fetchQuoteFn: async () => ({ c: 5, d: null, dp: null, t: 1e15 }) }),
    );
    const upsertArg = db.upsertPrices.mock.calls[0]![0] as Array<Record<string, unknown>>;
    // 1e15 s overflows the JS date range: every row falls back to `at`.
    for (const row of upsertArg) {
      expect(row.quoted_at).toBe(MON_OPEN.toISOString());
    }
  });
});
