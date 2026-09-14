import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { handleMarketData } from "./market-data";

/**
 * End-to-end coverage for the /v1/market/closes path with a real parquet
 * generation: sha256 verification, hyparquet parse, date filter, shape + sort.
 *
 * Deliberately plain `.js`, not `.ts`: this file needs `node:fs`/`node:crypto`,
 * which have no ambient declarations under this package's Workers-only
 * tsconfig (same reason as env-vars-pin.test.js). vitest still runs it via the
 * `.test.{ts,js}` glob.
 *
 * `fixtures/price-GLD.parquet` is a 403-byte generation written once with
 * hyparquet-writer (2 rows) and committed as a binary fixture, so no writer
 * dependency is added to package.json just to exercise the read path.
 */

const FIXTURE = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "fixtures", "price-GLD.parquet"),
);
const FIXTURE_BYTES = FIXTURE.buffer.slice(
  FIXTURE.byteOffset,
  FIXTURE.byteOffset + FIXTURE.byteLength,
);
const FIXTURE_SHA256 = createHash("sha256").update(FIXTURE).digest("hex");

const MANIFEST = {
  version: 1,
  as_of: "2026-09-11",
  datasets: {
    GLD: { object: "market-data/price/GLD/2026-09-11.parquet", sha256: FIXTURE_SHA256 },
  },
};

function fakeEnv() {
  return {
    MARKET_DATA: {
      get: async (key) => {
        if (key === "market-data/manifest.json") return { json: async () => MANIFEST };
        if (key === "market-data/price/GLD/2026-09-11.parquet") {
          return { arrayBuffer: async () => FIXTURE_BYTES };
        }
        return null;
      },
    },
  };
}

describe("handleMarketData end-to-end (real parquet fixture)", () => {
  it("parses a generation, resolves the ticker case-insensitively, and sorts", async () => {
    const url = new URL(
      "https://graph.digithings.ai/v1/market/closes?tickers=gld&from=2026-09-10&to=2026-09-11",
    );
    const res = await handleMarketData(new Request(url.toString()), fakeEnv(), url);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      as_of: "2026-09-11",
      rows: [
        { date: "2026-09-10", ticker: "GLD", close: 250 },
        { date: "2026-09-11", ticker: "GLD", close: 260 },
      ],
    });
  });

  it("drops rows outside the requested from/to window", async () => {
    const url = new URL(
      "https://graph.digithings.ai/v1/market/closes?tickers=GLD&from=2026-09-11&to=2026-09-11",
    );
    const res = await handleMarketData(new Request(url.toString()), fakeEnv(), url);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      as_of: "2026-09-11",
      rows: [{ date: "2026-09-11", ticker: "GLD", close: 260 }],
    });
  });
});
