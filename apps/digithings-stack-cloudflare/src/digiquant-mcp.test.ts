/**
 * Unit tests for the Worker-native digiquant market-data MCP (DIG-2913).
 *
 * The read path is asserted against a fake R2 bucket: parquet bytes are the
 * JSON of the row set (the injected decoder parses them back), so the test
 * exercises key layout, pointer/sha verification, window bounds, staleness and
 * the tool envelopes without a real parquet writer or the network.
 *
 * Parity anchors are the Python server's contracts:
 *   - `digiquant/src/digiquant/data/prices/refresh_gate.py` (trading days)
 *   - `digiquant/src/digiquant/mcp_server.py` (`_lookback_error`, envelopes,
 *     unknown ticker/series messages, 900s TTL, no cache on stale)
 */
import { describe, expect, it, vi } from "vitest";
import {
  boundedLookback,
  createDigiQuantMcpServer,
  handleDigiQuantMcp,
  listMarketData,
  lookbackError,
  macroPointerKey,
  normalizeTicker,
  type ParquetDecode,
  type R2BodyLike,
  type R2BucketLike,
  readMacroSeries,
  readPriceHistory,
  stalenessGate,
  TTL_MS,
  tradingDaysBetween,
} from "./digiquant-mcp";

const SEAL = "2026-10-20";
const enc = new TextEncoder();
const dec = new TextDecoder();

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function body(bytes: ArrayBuffer): R2BodyLike {
  return {
    arrayBuffer: async () => bytes,
    text: async () => dec.decode(bytes),
    json: async () => JSON.parse(dec.decode(bytes)),
  };
}

/** parquet stand-in: the object body IS the JSON row array. */
const decode: ParquetDecode = async (bytes) =>
  JSON.parse(dec.decode(bytes)) as Array<Record<string, unknown>>;

interface FakeStore {
  bucket: R2BucketLike;
  gets: string[];
  put(key: string, bytes: ArrayBuffer): void;
  putText(key: string, text: string): void;
}

function fakeBucket(): FakeStore {
  const objects = new Map<string, ArrayBuffer>();
  const gets: string[] = [];
  return {
    gets,
    put: (key, bytes) => void objects.set(key, bytes),
    putText: (key, text) => void objects.set(key, enc.encode(text).buffer as ArrayBuffer),
    bucket: {
      get: async (key) => {
        gets.push(key);
        const hit = objects.get(key);
        return hit === undefined ? null : body(hit);
      },
    },
  };
}

async function readJson(store: FakeStore, key: string): Promise<Record<string, any>> {
  const object = await store.bucket.get(key);
  expect(object).not.toBeNull();
  return (await object!.json()) as Record<string, any>;
}

function priceRows(ticker: string, dates: string[]): Array<Record<string, unknown>> {
  return dates.map((date, i) => ({
    date,
    ticker,
    open: 100 + i,
    high: 101 + i,
    low: 99 + i,
    close: 100.5 + i,
    volume: 1_000 + i,
  }));
}

/** Price generation + manifest entry for one ticker. */
async function seedPrice(
  store: FakeStore,
  manifest: { version: number; as_of: string; datasets: Record<string, unknown> },
  ticker: string,
  dates: string[],
): Promise<void> {
  const object = `market-data/price/${normalizeTicker(ticker)}/${dates[dates.length - 1]}.parquet`;
  const bytes = enc.encode(JSON.stringify(priceRows(ticker, dates))).buffer as ArrayBuffer;
  store.put(object, bytes);
  manifest.datasets[normalizeTicker(ticker)] = { object, sha256: await sha256Hex(bytes) };
}

/** Macro generation + pointer + manifest entry (millis-rounded obs dates). */
async function seedMacro(
  store: FakeStore,
  manifest: { version: number; as_of: string; datasets: Record<string, unknown> },
  seriesId: string,
  observations: Array<{ obs_date: string; value: number }>,
): Promise<void> {
  const object = `market-data/macro/fred__${seriesId}/${SEAL}.parquet`;
  const bytes = enc.encode(JSON.stringify(observations)).buffer as ArrayBuffer;
  store.put(object, bytes);
  store.putText(macroPointerKey("fred", seriesId), object);
  manifest.datasets[`fred__${seriesId}`] = { object, sha256: await sha256Hex(bytes) };
}

async function seedStore(): Promise<FakeStore> {
  const store = fakeBucket();
  const manifest = { version: 1, as_of: SEAL, datasets: {} as Record<string, unknown> };
  await seedPrice(store, manifest, "SPY", [
    "2026-10-14",
    "2026-10-15",
    "2026-10-16",
    "2026-10-19",
    "2026-10-20",
  ]);
  await seedMacro(store, manifest, "DGS10", [
    { obs_date: "2026-10-16", value: 4.11 },
    { obs_date: "2026-10-19", value: 4.07 },
    { obs_date: "2026-10-20", value: 4.02 },
  ]);
  store.putText("market-data/manifest.json", JSON.stringify(manifest));
  return store;
}

describe("staleness gate (Python refresh_gate parity)", () => {
  it("counts Mon-Fri only, seal-exclusive and run-inclusive", () => {
    // 2026-10-16 (Fri) -> 2026-10-20 (Tue): Mon 19, Tue 20 = 2 open days.
    expect(tradingDaysBetween("2026-10-16", "2026-10-20")).toBe(2);
    // Fri -> Sat -> Sun -> Mon: still 1 open day.
    expect(tradingDaysBetween("2026-10-16", "2026-10-19")).toBe(1);
    // A run date at or before the seal is fresh, never negative.
    expect(tradingDaysBetween("2026-10-20", "2026-10-20")).toBe(0);
    expect(tradingDaysBetween("2026-10-20", "2026-10-19")).toBe(0);
  });

  it("is fresh at the bound and stale one open day beyond it", () => {
    expect(stalenessGate("2026-10-12", "2026-10-19")).toEqual({ ok: true, stale_days: 5 });
    expect(stalenessGate("2026-10-09", "2026-10-19")).toEqual({ ok: false, stale_days: 6 });
  });
});

describe("argument handling (Python _lookback_error parity)", () => {
  it("rejects non-integers and anything below 1 instead of clamping silently", () => {
    for (const bad of [0, -1, 1.5, Number.NaN, "20", true, null]) {
      expect(lookbackError(bad)).toBe("lookback must be an integer >= 1");
    }
    expect(lookbackError(1)).toBeNull();
    expect(lookbackError(500)).toBeNull();
  });

  it("clamps a large window to 500", () => {
    expect(boundedLookback(9_999)).toBe(500);
    expect(boundedLookback(20)).toBe(20);
  });

  it("normalizes every slash, matching normalize_ticker", () => {
    expect(normalizeTicker("brk/b")).toBe("BRK-B");
    expect(normalizeTicker(" spy ")).toBe("SPY");
  });
});

describe("digiquant_get_price_history", () => {
  it("returns the newest lookback bars at the seal", async () => {
    const store = await seedStore();
    const payload = JSON.parse(
      await readPriceHistory({ bucket: store.bucket, decode }, { ticker: "SPY", lookback: 2 }),
    );
    expect(payload.as_of).toBe(SEAL);
    expect(payload.sealed_as_of).toBe(SEAL);
    expect(payload.stale).toBe(false);
    expect(payload.live_overlap).toBe("not_fetched");
    expect(payload.rows.map((row: { date: string }) => row.date)).toEqual([
      "2026-10-19",
      "2026-10-20",
    ]);
    expect(payload.rows[1]).toMatchObject({ ticker: "SPY", close: 104.5, open: 104 });
  });

  it("bounds a historical read at as_of", async () => {
    const store = await seedStore();
    const payload = JSON.parse(
      await readPriceHistory(
        { bucket: store.bucket, decode },
        { ticker: "SPY", lookback: 10, asOf: "2026-10-16" },
      ),
    );
    expect(payload.rows.map((row: { date: string }) => row.date)).toEqual([
      "2026-10-14",
      "2026-10-15",
      "2026-10-16",
    ]);
  });

  it("unknown ticker is the Python error envelope, not an empty window", async () => {
    const store = await seedStore();
    const payload = JSON.parse(
      await readPriceHistory({ bucket: store.bucket, decode }, { ticker: "NOPE" }),
    );
    expect(payload).toEqual({ error: "LookupError: unknown ticker 'NOPE'" });
  });

  it("refuses an as_of after the seal (no live fetch on this path)", async () => {
    const store = await seedStore();
    const payload = JSON.parse(
      await readPriceHistory(
        { bucket: store.bucket, decode },
        { ticker: "SPY", asOf: "2026-10-21" },
      ),
    );
    expect(payload.error).toContain("after the sealed generation 2026-10-20");
    expect(payload.error).toContain("no live fetch");
  });

  it("never serves an as_of it cannot honour as fresh", async () => {
    // The Worker path is seal-bounded, so `stale` is false whenever the read
    // succeeds. The "is the cache current?" signal is `stale_today` on
    // digiquant_list_market_data (next describe), not this field.
    const store = await seedStore();
    const payload = JSON.parse(
      await readPriceHistory(
        { bucket: store.bucket, decode },
        { ticker: "SPY", asOf: "2026-10-19" },
      ),
    );
    expect(payload.stale).toBe(false);
  });

  it("fails loud on a digest mismatch", async () => {
    const store = await seedStore();
    const manifest = await readJson(store, "market-data/manifest.json");
    manifest.datasets.SPY.sha256 = "0".repeat(64);
    store.putText("market-data/manifest.json", JSON.stringify(manifest));
    const payload = JSON.parse(
      await readPriceHistory({ bucket: store.bucket, decode }, { ticker: "SPY" }),
    );
    expect(payload.error).toContain("sha256 mismatch");
  });
});

describe("digiquant_list_market_data", () => {
  it("lists price tickers and macro series with a today-relative staleness flag", async () => {
    const store = await seedStore();
    // 2026-10-20 + 6 open trading days = 2026-10-28.
    const fresh = JSON.parse(
      await listMarketData({
        bucket: store.bucket,
        decode,
        now: () => Date.parse("2026-10-23T00:00:00Z"),
      }),
    );
    expect(fresh).toMatchObject({
      as_of: SEAL,
      version: 1,
      tickers: ["SPY"],
      macro_series: ["fred__DGS10"],
    });
    expect(fresh.stale_today).toBe(false);

    const stale = JSON.parse(
      await listMarketData({
        bucket: store.bucket,
        decode,
        now: () => Date.parse("2026-10-29T00:00:00Z"),
      }),
    );
    expect(stale.stale_today).toBe(true);
  });

  it("surfaces an unsupported manifest version instead of guessing", async () => {
    const store = await seedStore();
    store.putText(
      "market-data/manifest.json",
      JSON.stringify({ version: 2, as_of: SEAL, datasets: {} }),
    );
    const payload = JSON.parse(await listMarketData({ bucket: store.bucket, decode }));
    expect(payload).toEqual({ error: "unsupported manifest version 2" });
  });
});

describe("digiquant_get_macro_series", () => {
  it("returns the Python envelope shape {as_of, series, stale}", async () => {
    const store = await seedStore();
    const payload = JSON.parse(
      await readMacroSeries(
        { bucket: store.bucket, decode },
        { seriesIds: ["DGS10"], lookback: 2 },
      ),
    );
    expect(Object.keys(payload).sort()).toEqual(["as_of", "series", "stale"]);
    expect(payload.as_of).toBe(SEAL);
    expect(payload.stale).toBe(false);
    expect(payload.series.DGS10.latest).toEqual({ obs_date: "2026-10-20", value: 4.02 });
    expect(payload.series.DGS10.window.map((row: { obs_date: string }) => row.obs_date)).toEqual([
      "2026-10-19",
      "2026-10-20",
    ]);
  });

  it("unknown series is an error envelope, never an empty window", async () => {
    const store = await seedStore();
    const payload = JSON.parse(
      await readMacroSeries({ bucket: store.bucket, decode }, { seriesIds: ["NOPE"] }),
    );
    expect(payload).toEqual({ error: "LookupError: unknown macro series 'NOPE'" });
  });

  it("rejects an empty series list", async () => {
    const store = await seedStore();
    const payload = JSON.parse(
      await readMacroSeries({ bucket: store.bucket, decode }, { seriesIds: [] }),
    );
    expect(payload).toEqual({ error: "series_ids must be a non-empty array" });
  });
});

describe("900s cache (Python TTL parity)", () => {
  it("caches a fresh payload for 900s instead of re-reading R2", async () => {
    const store = await seedStore();
    const cache = new Map();
    const deps = { bucket: store.bucket, decode, cache };
    await readPriceHistory(deps, { ticker: "SPY", lookback: 2 });
    // manifest + payload entries
    expect(cache.size).toBe(2);
    const afterFirst = store.gets.length;
    const second = JSON.parse(await readPriceHistory(deps, { ticker: "SPY", lookback: 2 }));
    expect(store.gets.length).toBe(afterFirst);
    expect(second.rows.length).toBe(2);
  });

  it("re-reads after the TTL expires", async () => {
    const store = await seedStore();
    const cache = new Map();
    let now = 1_000_000;
    const deps = { bucket: store.bucket, decode, cache, now: () => now };
    await readPriceHistory(deps, { ticker: "SPY", lookback: 2 });
    const afterFirst = store.gets.length;
    now += TTL_MS;
    await readPriceHistory(deps, { ticker: "SPY", lookback: 2 });
    expect(store.gets.length).toBeGreaterThan(afterFirst);
  });
});

describe("edge routing (/mcp, auth, health)", () => {
  const edgeKey = "test-edge-key";

  function request(path: string, init: RequestInit = {}): Request {
    return new Request(`https://mcp.digithings.ai${path}`, init);
  }

  it("answers liveness without the edge key", async () => {
    const store = await seedStore();
    const res = await handleDigiQuantMcp(request("/healthz"), {
      bucket: store.bucket,
      edgeKey,
      decode,
    });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ status: "ok", service: "digiquant-mcp", backend: "r2" });
  });

  it("fails closed without a configured key or with a wrong one", async () => {
    const store = await seedStore();
    const unconfigured = await handleDigiQuantMcp(request("/mcp", { method: "POST", body: "{}" }), {
      bucket: store.bucket,
      edgeKey: undefined,
    });
    expect(unconfigured.status).toBe(503);

    const unauthorized = await handleDigiQuantMcp(request("/mcp", { method: "POST", body: "{}" }), {
      bucket: store.bucket,
      edgeKey,
    });
    expect(unauthorized.status).toBe(401);

    const wrong = await handleDigiQuantMcp(
      request("/mcp", { method: "POST", body: "{}", headers: { "x-digi-mcp-key": "nope" } }),
      { bucket: store.bucket, edgeKey },
    );
    expect(wrong.status).toBe(401);
  });

  it("takes the digikey JWT path when a bearer token is presented", async () => {
    const store = await seedStore();
    const res = await handleDigiQuantMcp(
      request("/mcp", {
        method: "POST",
        body: "{}",
        headers: { authorization: "Bearer not.a.jwt" },
      }),
      { bucket: store.bucket, edgeKey },
    );
    // Malformed token is refused (401) rather than falling back to a success.
    expect(res.status).toBe(401);
    expect(res.headers.get("www-authenticate")).toContain("digikey");

    // A JWT path configured without a static key is still gated: an empty key
    // never means "match anything".
    const jwtOnly = await handleDigiQuantMcp(request("/mcp", { method: "POST", body: "{}" }), {
      bucket: store.bucket,
      edgeKey: undefined,
      authEnv: { DIGIKEY_JWKS_URL: "https://key.digithings.ai/.well-known/jwks.json" },
    });
    expect(jwtOnly.status).toBe(401);
  });

  it("404s an unknown path and 405s a GET on /mcp", async () => {
    const store = await seedStore();
    const notFound = await handleDigiQuantMcp(request("/other"), { bucket: store.bucket, edgeKey });
    expect(notFound.status).toBe(404);

    const wrongMethod = await handleDigiQuantMcp(
      request("/mcp", { headers: { "x-digi-mcp-key": edgeKey } }),
      { bucket: store.bucket, edgeKey, cache: new Map() },
    );
    expect(wrongMethod.status).toBe(405);
  });

  it("serves tools/list and tools/call over the real MCP transport", async () => {
    const store = await seedStore();
    const options = { bucket: store.bucket, edgeKey, cache: new Map(), decode };
    // MCP requires both response types in Accept; the server answers JSON.
    const headers = {
      "x-digi-mcp-key": edgeKey,
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
    };

    const list = await handleDigiQuantMcp(
      request("/mcp", {
        method: "POST",
        headers,
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }),
      }),
      options,
    );
    expect(list.status).toBe(200);
    const listed = (await list.json()) as { result: { tools: Array<{ name: string }> } };
    expect(listed.result.tools.map((tool) => tool.name).sort()).toEqual([
      "digiquant_get_macro_series",
      "digiquant_get_price_history",
      "digiquant_list_market_data",
    ]);

    const call = await handleDigiQuantMcp(
      request("/mcp", {
        method: "POST",
        headers,
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 2,
          method: "tools/call",
          params: {
            name: "digiquant_get_price_history",
            arguments: { ticker: "SPY", lookback: 1 },
          },
        }),
      }),
      options,
    );
    expect(call.status).toBe(200);
    const called = (await call.json()) as {
      result: { content: Array<{ type: string; text: string }>; isError?: boolean };
    };
    expect(called.result.isError).not.toBe(true);
    const payload = JSON.parse(called.result.content[0].text);
    expect(payload.rows).toHaveLength(1);
    expect(payload.rows[0].date).toBe(SEAL);
  });

  it("returns isError for a tool failure (unknown ticker) instead of throwing", async () => {
    const store = await seedStore();
    const res = await handleDigiQuantMcp(
      request("/mcp", {
        method: "POST",
        headers: {
          "x-digi-mcp-key": edgeKey,
          "content-type": "application/json",
          accept: "application/json, text/event-stream",
        },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 3,
          method: "tools/call",
          params: { name: "digiquant_get_price_history", arguments: { ticker: "NOPE" } },
        }),
      }),
      { bucket: store.bucket, edgeKey, cache: new Map(), decode },
    );
    const body = (await res.json()) as {
      result: { content: Array<{ text: string }>; isError?: boolean };
    };
    expect(body.result.isError).toBe(true);
    expect(JSON.parse(body.result.content[0].text)).toEqual({
      error: "LookupError: unknown ticker 'NOPE'",
    });
  });
});

describe("server construction", () => {
  it("builds without touching R2 (no eager manifest read)", () => {
    const get = vi.fn();
    const server = createDigiQuantMcpServer({ bucket: { get } });
    expect(server).toBeTruthy();
    expect(get).not.toHaveBeenCalled();
  });
});
