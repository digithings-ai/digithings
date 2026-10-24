import { describe, expect, it, vi } from "vitest";
import worker from "./index";
import { pickBackend, SupabaseBackend } from "./backends";
import { BadRequest, parseSelect, selectSql, upsertSql, validateUpsert } from "./query";
import { TWELVEX_TABLES } from "./tables.twelvex";

const [T, spec] = Object.entries(TWELVEX_TABLES).find(([, s]) => s.pk.length > 0)!;
const C0 = spec.columns[0];
const env = { DATA_API_TOKEN: "t0k", SUPABASE_TWELVEX_URL: "https://x.supabase.co", SUPABASE_TWELVEX_SERVICE_KEY: "k" };

describe("auth", () => {
  it("fails closed without token config", async () => {
    const r = await worker.fetch(new Request(`https://d/v1/twelvex/${T}`), {} as never);
    expect(r.status).toBe(401);
  });
  it("rejects wrong bearer", async () => {
    const r = await worker.fetch(new Request(`https://d/v1/twelvex/${T}`, { headers: { authorization: "Bearer nope" } }), env as never);
    expect(r.status).toBe(401);
  });
  it("health is open and reports default supabase", async () => {
    const r = await worker.fetch(new Request("https://d/v1/health"), {} as never);
    expect(await r.json()).toEqual({ ok: true, backend: "supabase" });
  });
  it("unknown table 404", async () => {
    const r = await worker.fetch(new Request("https://d/v1/twelvex/pg_shadow", { headers: { authorization: "Bearer t0k" } }), env as never);
    expect(r.status).toBe(404);
  });
});

describe("query building", () => {
  it("rejects unknown columns (no identifier injection)", () => {
    expect(() => parseSelect(T, spec, new URLSearchParams({ 'x" OR 1=1 --': "eq.1" }))).toThrow(BadRequest);
    expect(() => parseSelect(T, spec, new URLSearchParams({ order: "evil.desc" }))).toThrow(BadRequest);
  });
  it("builds parameterized SQL", () => {
    const q = parseSelect(T, spec, new URLSearchParams([[C0, "eq.a'b"], ["order", `${C0}.desc`], ["limit", "5000"]]));
    const { sql, binds } = selectSql(q);
    expect(sql).toBe(`SELECT * FROM "${T}" WHERE "${C0}" = ? ORDER BY "${C0}" DESC LIMIT 1000`);
    expect(binds).toEqual(["a'b"]);
  });
  it("upsert uses pk by default and encodes json/bool", () => {
    const row = Object.fromEntries(spec.columns.slice(0, 3).map((c, i) => [c, i === 0 ? { a: 1 } : i === 1 ? true : "x"]));
    const q = validateUpsert(T, spec, [row], null);
    expect(q.onConflict).toEqual(spec.pk);
    const { sql, binds } = upsertSql(q, row);
    expect(sql).toContain(`ON CONFLICT (${spec.pk.map((c) => `"${c}"`).join(",")})`);
    expect(binds[0]).toBe('{"a":1}');
    expect(binds[1]).toBe(1);
  });
  it("caps batch size", () => {
    expect(() => validateUpsert(T, spec, [], null)).toThrow(BadRequest);
    const c0 = spec.columns[0];
    expect(() => validateUpsert(T, spec, Array.from({ length: 501 }, () => ({ [c0]: 1 })), null)).toThrow(BadRequest);
    expect(() => validateUpsert(T, spec, Array.from({ length: 500 }, () => ({ [c0]: 1 })), null)).not.toThrow();
  });
  // #5404: an empty row would build `INSERT INTO "t" () VALUES ()` (a syntax
  // error, so a 502 rather than a 400), and rows with different key sets mean
  // different things per DATA_BACKEND. Both are refused instead.
  it("refuses a row with no columns", () => {
    expect(() => validateUpsert(T, spec, {}, null)).toThrow(BadRequest);
    expect(() => validateUpsert(T, spec, [{}], null)).toThrow(BadRequest);
    expect(() => validateUpsert(T, spec, [{ [spec.columns[0]]: 1 }, {}], null)).toThrow(BadRequest);
  });
  it("refuses rows with different key sets", () => {
    const [a, b] = spec.columns;
    expect(() => validateUpsert(T, spec, [{ [a]: 1 }, { [b]: 2 }], null)).toThrow(BadRequest);
    // The guard is on the SET of keys, not their order, and a uniform batch of
    // any size still passes -- so it is not refusing every multi-row call.
    expect(() => validateUpsert(T, spec, [{ [b]: 1, [a]: 2 }], null)).not.toThrow();
    expect(() => validateUpsert(T, spec, [{ [a]: 1, [b]: 2 }, { [b]: 3, [a]: 4 }], null)).not.toThrow();
  });
});

describe("backend switch", () => {
  it("defaults to supabase", () => expect(pickBackend(env, "twelvex").name).toBe("supabase"));
  it("d1 needs binding", () => expect(() => pickBackend({ ...env, DATA_BACKEND: "d1" }, "twelvex")).toThrow());
  it("rejects unknown mode", () => expect(() => pickBackend({ ...env, DATA_BACKEND: "pg" }, "twelvex")).toThrow());
  it("supabase select maps to PostgREST", async () => {
    const f = vi.fn(async () => new Response("[]"));
    const b = new SupabaseBackend("https://x.supabase.co", "k", f as never);
    await b.select(parseSelect(T, spec, new URLSearchParams([[C0, "in.(a,b)"], ["limit", "2"]])));
    expect(String((f.mock.calls[0] as unknown[])[0])).toBe(`https://x.supabase.co/rest/v1/${T}?${C0}=in.%28a%2Cb%29&limit=2`);
  });
});
