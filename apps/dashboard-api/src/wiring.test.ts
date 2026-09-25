/**
 * Slice 0006 wiring tests: every contracted route is reachable through the
 * worker dispatch over the stub doubles (no network, no secrets).
 */
import { describe, expect, it } from "vitest";
import app, { type Env } from "./index";
import { STUB_NULL_AS_OF } from "./stubs";

const NO_ENV: Env = {};
const get = (path: string) => new Request(`https://x${path}`);

async function bodyOf(res: Response): Promise<Record<string, unknown>> {
  return (await res.json()) as Record<string, unknown>;
}

describe("wired contracted routes", () => {
  const cases: Array<{ path: string; dataKey: string }> = [
    { path: "/allocations", dataKey: "rows" },
    { path: "/nav-series", dataKey: "points" },
    { path: "/brief?overlay=off", dataKey: "book_as_of" },
    { path: "/performance", dataKey: "nav" },
    { path: "/kpis/live", dataKey: "universe" },
    { path: "/benchmarks?tickers=SPY", dataKey: "universe" },
    { path: "/ledger", dataKey: "events" },
  ];
  for (const { path, dataKey } of cases) {
    it(`GET ${path} returns 200 with the §1 envelope`, async () => {
      const res = await app.fetch(get(path), NO_ENV);
      expect(res.status).toBe(200);
      const body = await bodyOf(res);
      expect(body).toHaveProperty("data");
      expect(body).toHaveProperty("as_of");
      expect(body).toHaveProperty("retrieval_pin");
      expect(body).toHaveProperty("provenance");
      expect(body.data as Record<string, unknown>).toHaveProperty(dataKey);
    });
  }

  it("echoes retrieval_pin on a wired route", async () => {
    const res = await app.fetch(get("/brief?retrieval_pin=rp-7"), NO_ENV);
    expect(res.status).toBe(200);
    expect((await bodyOf(res)).retrieval_pin).toBe("rp-7");
  });

  it("reaches not_found through the stub null-book convention", async () => {
    const res = await app.fetch(get(`/brief?asOf=${STUB_NULL_AS_OF}`), NO_ENV);
    expect(res.status).toBe(404);
    const body = (await res.json()) as { error: { code: string } };
    expect(body.error.code).toBe("not_found");
  });

  it("serves an honest empty ledger range as success with []", async () => {
    const res = await app.fetch(get("/ledger?ticker=NOPE"), NO_ENV);
    expect(res.status).toBe(200);
    const body = (await res.json()) as { data: { events: unknown[] } };
    expect(body.data.events).toEqual([]);
  });

  it("keeps scaffold behavior: /healthz live, unknown routes 400, no /book-date", async () => {
    expect((await app.fetch(get("/healthz"), NO_ENV)).status).toBe(200);
    expect((await app.fetch(get("/nope"), NO_ENV)).status).toBe(400);
    expect((await app.fetch(get("/book-date"), NO_ENV)).status).toBe(400);
  });
});
