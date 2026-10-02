import { afterEach, describe, expect, it, vi } from "vitest";
import { tableRead, tableRows, twelvexEnv, twelvexRead, type TableReadEnv } from "./table-read";

const CORE: TableReadEnv = { SUPABASE_URL: "https://core.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "core-key" };
const BOTH: TableReadEnv = { ...CORE, TWELVEX_SUPABASE_URL: "https://tx.supabase.co/", TWELVEX_SUPABASE_SERVICE_KEY: "tx-key" };

const calls: Array<{ url: string; key: string | null }> = [];
function mockFetch(out: unknown, status = 200): void {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: { headers?: Record<string, string> }) => {
    calls.push({ url, key: init?.headers?.apikey ?? null });
    return Response.json(out, { status });
  }));
}
afterEach(() => {
  calls.length = 0;
  vi.unstubAllGlobals();
});

describe("tableRead (core)", () => {
  it("returns the standard envelope with as_of from the field", async () => {
    mockFetch([{ date: "2026-08-27", v: 1 }, { date: "2026-08-28", v: 2 }]);
    const res = await tableRead(CORE, { table: "theses", query: "select=*&limit=2", asOfField: "date", retrievalPin: "p1" });
    expect(res.status).toBe(200);
    const body = (await res.json()) as Record<string, any>;
    expect(body.data).toHaveLength(2);
    expect(body.as_of).toBe("2026-08-28");
    expect(body.retrieval_pin).toBe("p1");
    expect(body.provenance).toMatchObject({ source: "core:theses", tip_date: "2026-08-28", marks: "unavailable" });
    expect(calls[0]).toEqual({ url: "https://core.supabase.co/rest/v1/theses?select=*&limit=2", key: "core-key" });
  });
  it("null as_of when no field is given; provenance can be overridden", async () => {
    mockFetch([{ a: 1 }]);
    const body = (await (await tableRead(CORE, { table: "t", provenance: { source: "custom" } })).json()) as Record<string, any>;
    expect(body.as_of).toBeNull();
    expect(body.provenance.source).toBe("custom");
  });
  it("fails closed with upstream_empty when unconfigured (no fetch)", async () => {
    mockFetch([]);
    const res = await tableRead({}, { table: "theses" });
    expect(res.status).toBe(502);
    expect(((await res.json()) as any).error.code).toBe("upstream_empty");
    expect(calls).toHaveLength(0);
  });
  it("fails closed on empty rows unless allowEmpty", async () => {
    mockFetch([]);
    expect((await tableRead(CORE, { table: "t" })).status).toBe(502);
    const ok = await tableRead(CORE, { table: "t", allowEmpty: true });
    expect(ok.status).toBe(200);
    expect(((await ok.json()) as any).data).toEqual([]);
  });
  it("maps upstream HTTP errors and non-list bodies to upstream_empty", async () => {
    mockFetch({ message: "nope" }, 500);
    const res = await tableRead(CORE, { table: "t" });
    expect(res.status).toBe(502);
    expect(((await res.json()) as any).error.details.upstream_status).toBe(500);
    mockFetch({ not: "a list" });
    expect((await tableRead(CORE, { table: "t" })).status).toBe(502);
  });
  it("tableRows exposes raw rows for reshaping handlers", async () => {
    mockFetch([{ a: 1 }]);
    expect(await tableRows(CORE, { table: "t" })).toEqual({ rows: [{ a: 1 }] });
  });
});

describe("twelve-x reader", () => {
  it("uses its own url and key, never the core ones", async () => {
    mockFetch([{ pair: "EURUSD", ts: "2026-08-28T10:00:00Z" }]);
    const res = await twelvexRead(BOTH, { table: "ideas", query: "select=*", asOfField: "ts" });
    expect(res.status).toBe(200);
    expect(calls[0]).toEqual({ url: "https://tx.supabase.co/rest/v1/ideas?select=*", key: "tx-key" });
    const body = (await res.json()) as Record<string, any>;
    expect(body.provenance.source).toBe("twelvex:ideas");
    expect(body.as_of).toBe("2026-08-28");
  });
  it("absent twelve-x env fails closed even when core is configured", async () => {
    mockFetch([{ a: 1 }]);
    const res = await twelvexRead(CORE, { table: "ideas" });
    expect(res.status).toBe(502);
    expect(calls).toHaveLength(0);
    expect(twelvexEnv(CORE)).toBeNull();
    expect(twelvexEnv({ TWELVEX_SUPABASE_URL: "https://tx" })).toBeNull();
  });
});
