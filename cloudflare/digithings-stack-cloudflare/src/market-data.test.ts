import { describe, expect, it } from "vitest";
import {
  corsHeaders,
  handleMarketData,
  manifestTickers,
  resolvePointer,
  shapeCloses,
} from "./market-data";

const MANIFEST = {
  version: 1,
  as_of: "2026-09-11",
  datasets: {
    GLD: { object: "market-data/price/GLD/2026-09-11.parquet", sha256: "a".repeat(64) },
    SPY: { object: "market-data/price/SPY/2026-09-11.parquet", sha256: "b".repeat(64) },
    "fred__DGS10": { object: "market-data/macro/fred__DGS10/2026-09-11.parquet", sha256: "c".repeat(64) },
  },
};

describe("market-data helpers", () => {
  it("lists only price datasets", () => {
    expect(manifestTickers(MANIFEST).sort()).toEqual(["GLD", "SPY"]);
  });

  it("resolves a ticker entry case-insensitively", () => {
    expect(resolvePointer(MANIFEST, "gld")?.object).toContain("/GLD/");
    expect(resolvePointer(MANIFEST, "BRK/B")).toBeUndefined();
  });

  it("does not resolve macro dataset ids as tickers", () => {
    expect(resolvePointer(MANIFEST, "fred__DGS10")).toBeUndefined();
    expect(resolvePointer(MANIFEST, "FRED__DGS10")).toBeUndefined();
  });

  it("shapes and sorts close rows", () => {
    expect(
      shapeCloses([
        { date: "2026-09-11", ticker: "GLD", close: 260 },
        { date: "2026-09-10", ticker: "GLD", close: 250 },
      ]),
    ).toEqual([
      { date: "2026-09-10", ticker: "GLD", close: 250 },
      { date: "2026-09-11", ticker: "GLD", close: 260 },
    ]);
  });

  it("emits CORS only for allow-listed origins", () => {
    expect(corsHeaders("https://digiquant.io", ["https://digiquant.io"])["Access-Control-Allow-Origin"]).toBe(
      "https://digiquant.io",
    );
    expect(corsHeaders("https://evil.example", ["https://digiquant.io"])["Access-Control-Allow-Origin"]).toBeUndefined();
  });
});

const MANIFEST_OBJECT = { json: async () => MANIFEST };

function fakeEnv(objects: Record<string, unknown>) {
  return {
    MARKET_DATA: {
      get: async (key: string) => objects[key] ?? null,
    } as unknown as R2Bucket,
  };
}

describe("handleMarketData", () => {
  it("serves tickers with as_of, allow-listed CORS and a cache header", async () => {
    const url = new URL("https://graph.digithings.ai/v1/market/tickers");
    const res = await handleMarketData(
      new Request(url.toString(), { headers: { Origin: "https://digiquant.io" } }),
      fakeEnv({ "market-data/manifest.json": MANIFEST_OBJECT }),
      url,
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe("https://digiquant.io");
    expect(res.headers.get("Cache-Control")).toBe("public, max-age=300");
    expect(await res.json()).toEqual({ as_of: "2026-09-11", tickers: ["GLD", "SPY"] });
  });

  it("answers an OPTIONS preflight with 204 before touching R2", async () => {
    const url = new URL("https://graph.digithings.ai/v1/market/closes");
    const res = await handleMarketData(
      new Request(url.toString(), { method: "OPTIONS", headers: { Origin: "https://digithings.ai" } }),
      fakeEnv({}),
      url,
    );
    expect(res.status).toBe(204);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe("https://digithings.ai");
  });

  it("returns 503 when the manifest object is missing", async () => {
    const url = new URL("https://graph.digithings.ai/v1/market/tickers");
    const res = await handleMarketData(new Request(url.toString()), fakeEnv({}), url);
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: "manifest missing" });
  });

  it("requires at least one ticker for closes", async () => {
    const url = new URL("https://graph.digithings.ai/v1/market/closes");
    const res = await handleMarketData(
      new Request(url.toString()),
      fakeEnv({ "market-data/manifest.json": MANIFEST_OBJECT }),
      url,
    );
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: "tickers required" });
  });

  it("skips unknown tickers and returns an empty row set", async () => {
    const url = new URL("https://graph.digithings.ai/v1/market/closes?tickers=BRK/B");
    const res = await handleMarketData(
      new Request(url.toString()),
      fakeEnv({ "market-data/manifest.json": MANIFEST_OBJECT }),
      url,
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ as_of: "2026-09-11", rows: [] });
  });

  it("treats a macro dataset id as an unknown ticker instead of parsing it", async () => {
    const url = new URL("https://graph.digithings.ai/v1/market/closes?tickers=fred__DGS10");
    const res = await handleMarketData(
      new Request(url.toString()),
      fakeEnv({
        "market-data/manifest.json": MANIFEST_OBJECT,
        // A macro object whose bytes must never be fetched: same 404-ish shape
        // as an unknown ticker, never a parquet parse or a throw.
        "market-data/macro/fred__DGS10/2026-09-11.parquet": {
          arrayBuffer: async () => {
            throw new Error("macro parquet must never be read");
          },
        },
      }),
      url,
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ as_of: "2026-09-11", rows: [] });
  });

  it("rejects a generation whose sha256 does not match the manifest", async () => {
    const url = new URL("https://graph.digithings.ai/v1/market/closes?tickers=GLD");
    const res = await handleMarketData(
      new Request(url.toString()),
      fakeEnv({
        "market-data/manifest.json": MANIFEST_OBJECT,
        "market-data/price/GLD/2026-09-11.parquet": {
          arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
        },
      }),
      url,
    );
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "sha mismatch for GLD" });
  });
});
