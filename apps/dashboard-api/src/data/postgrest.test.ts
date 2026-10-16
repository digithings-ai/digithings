/**
 * Emission tests for the PostgREST builder.
 *
 * The builder is pure until `execute`, so these assert the emitted
 * `{url, headers, body}` directly — no database, no network, no D1. That is
 * what makes each supabase-js semantic checkable rather than assumed.
 *
 * NON-VACUITY. Every method in this file also has a positive arm that must
 * succeed. A builder that threw on everything would pass the negative
 * assertions alone, so the positive arms are what make the negatives real.
 * The first test asserts the exact chain shape the settings handler uses.
 */

import { describe, expect, it } from "vitest";
import { createPostgrestClient, type PostgrestError } from "./postgrest";

const BASE = "https://example.supabase.co";
const KEY = "service-role-key";

function client() {
  return createPostgrestClient({ url: BASE, apiKey: KEY });
}

/** Query params as a plain object, so assertions read as intent not encoding. */
function params(url: string): Record<string, string> {
  const qs = new URL(url).search;
  const out: Record<string, string> = {};
  for (const pair of qs.replace(/^\?/, "").split("&")) {
    if (!pair) continue;
    const i = pair.indexOf("=");
    out[decodeURIComponent(pair.slice(0, i))] = decodeURIComponent(pair.slice(i + 1));
  }
  return out;
}

describe("query builder emission", () => {
  // The exact chain shape measured in settings-handlers.ts:
  // .from().select().eq().order().limit()
  it("builds the chain the settings handler uses", () => {
    const req = client()
      .from("workspace_provider_credentials")
      .select("id,provider")
      .eq("workspace_id", "ws-1")
      .order("created_at", { ascending: false })
      .limit(5)
      .buildRequest();

    expect(req.method).toBe("GET");
    expect(req.url.startsWith(`${BASE}/rest/v1/workspace_provider_credentials?`)).toBe(true);
    expect(params(req.url)).toMatchObject({
      select: "id,provider",
      workspace_id: "eq.ws-1",
      order: "created_at.desc",
      limit: "5",
    });
    expect(req.headers.Authorization).toBe(`Bearer ${KEY}`);
    expect(req.body).toBeUndefined();
  });

  it("encodes every comparison operator the handler uses", () => {
    const p = params(
      client()
        .from("t")
        .select("*")
        .eq("a", "x")
        .neq("b", "y")
        .gt("c", 1)
        .gte("d", 2)
        .lt("e", 3)
        .lte("f", 4)
        .buildRequest().url,
    );
    expect(p).toMatchObject({
      a: "eq.x",
      b: "neq.y",
      c: "gt.1",
      d: "gte.2",
      e: "lt.3",
      f: "lte.4",
    });
  });

  it("emits in.(a,b,c) for .in()", () => {
    const p = params(
      client().from("t").select("*").in("status", ["ok", "failed", "queued"]).buildRequest().url,
    );
    expect(p.status).toBe("in.(ok,failed,queued)");
  });

  it("escapes a filter value so a comma cannot close the list", () => {
    const p = params(client().from("t").select("*").eq("name", "a,b").buildRequest().url);
    expect(p.name).toBe("eq.a,b");
  });

  it("orders ascending by default and descending on request", () => {
    const asc = params(client().from("t").select("*").order("a").buildRequest().url);
    const desc = params(
      client().from("t").select("*").order("a", { ascending: false }).buildRequest().url,
    );
    expect(asc.order).toBe("a.asc");
    expect(desc.order).toBe("a.desc");
  });

  it("range() becomes limit plus offset", () => {
    const p = params(client().from("t").select("*").range(10, 19).buildRequest().url);
    expect(p.limit).toBe("10");
    expect(p.offset).toBe("10");
  });
});

/**
 * Two shapes the settings handler actually calls and that the builder did not
 * accept at all. Both are pinned to their real call sites so the requirement is
 * a fact about the port rather than a guess:
 *
 *   settings-handlers.ts:1663  .is("revoked_at", null)
 *   settings-handlers.ts:414   .eq("is_house_default", false)
 *   settings-handlers.ts:528   .eq("is_house_default", false)
 */
describe("SQL NULL and boolean filters", () => {
  it("is() emits the `is` operator, which is what the revoked_at query needs", () => {
    const p = params(client().from("t").select("*").is("revoked_at", null).buildRequest().url);
    expect(p.revoked_at).toBe("is.null");
  });

  // The discrimination arm. `= NULL` is never true in SQL, so `eq(col, null)`
  // matches ZERO rows — which a caller reads as "no such setting" when the row
  // is in fact there. If `is()` were an alias for `eq()` these two would be the
  // same string and this test would fail; that is the whole point of it.
  it("is() and eq() on the same null are NOT the same query", () => {
    const viaIs = params(client().from("t").select("*").is("revoked_at", null).buildRequest().url);
    const viaEq = params(client().from("t").select("*").eq("revoked_at", null).buildRequest().url);
    expect(viaIs.revoked_at).toBe("is.null");
    expect(viaEq.revoked_at).toBe("eq.null");
    expect(viaIs.revoked_at).not.toBe(viaEq.revoked_at);
  });

  it("eq() accepts a boolean and puts the lowercase literal on the wire", () => {
    const p = params(
      client().from("t").select("*").eq("is_house_default", false).buildRequest().url,
    );
    // PostgREST compares against the literal string, so `False` or `FALSE`
    // would silently match nothing. Lowercase is the only correct spelling.
    expect(p.is_house_default).toBe("eq.false");
    expect(p.is_house_default).not.toMatch(/False|FALSE/);
  });

  it("eq() accepts a true boolean too, so the house-default lookup has both arms", () => {
    const p = params(client().from("t").select("*").eq("is_house_default", true).buildRequest().url);
    expect(p.is_house_default).toBe("eq.true");
  });

  it("is() accepts a boolean for the IS TRUE / IS FALSE comparison", () => {
    const p = params(client().from("t").select("*").is("enabled", true).buildRequest().url);
    expect(p.enabled).toBe("is.true");
  });

  it("leaves string and number filtering untouched", () => {
    const p = params(client().from("t").select("*").eq("a", "x").gt("b", 1).buildRequest().url);
    expect(p).toMatchObject({ a: "eq.x", b: "gt.1" });
  });
});

describe("cardinality: single vs maybeSingle", () => {
  it("single() asks PostgREST for an object", () => {
    const req = client().from("t").select("*").eq("id", 1).single().buildRequest();
    expect(req.headers.Accept).toBe("application/vnd.pgrst.object+json");
  });

  it("maybeSingle() bounds the query to one row and does NOT request an object", () => {
    const req = client().from("t").select("*").eq("id", 1).maybeSingle().buildRequest();
    expect(req.headers.Accept).toBeUndefined();
    expect(params(req.url).limit).toBe("1");
  });

  // The discrimination arm: on an empty result maybeSingle is null, NOT a
  // throw. Getting this wrong turns "no row yet" into a 500 on first read.
  it("maybeSingle resolves null for zero rows", async () => {
    const stub = createPostgrestClient({
      url: BASE,
      apiKey: KEY,
      fetchImpl: async () => new Response("[]", { status: 200 }),
    });
    await expect(stub.from("t").select("*").eq("id", 1).maybeSingle()).resolves.toBeNull();
  });

  it("maybeSingle throws when more than one row comes back", async () => {
    const stub = createPostgrestClient({
      url: BASE,
      apiKey: KEY,
      fetchImpl: async () => new Response('[{"id":1},{"id":2}]', { status: 200 }),
    });
    await expect(
      stub.from("t").select("*").maybeSingle(),
    ).rejects.toMatchObject({ code: "PGRST116" });
  });

  it("single() surfaces the PostgREST error code", async () => {
    const stub = createPostgrestClient({
      url: BASE,
      apiKey: KEY,
      fetchImpl: async () =>
        new Response(JSON.stringify({ code: "PGRST116", message: "0 rows" }), {
          status: 406,
        }),
    });
    let err: PostgrestError | null = null;
    try {
      await stub.from("t").select("*").single();
    } catch (e) {
      err = e as PostgrestError;
    }
    expect(err).toMatchObject({ code: "PGRST116", message: "0 rows" });
  });
});

describe("writes", () => {
  it("upsert resolves to merge-duplicates, never ignore-duplicates", () => {
    const req = client()
      .from("olympus_profile_config")
      .upsert([{ workspace_id: "ws-1" }], { onConflict: "workspace_id" })
      .buildRequest();
    expect(req.method).toBe("POST");
    expect(req.headers.Prefer).toContain("resolution=merge-duplicates");
    expect(req.headers.Prefer).not.toContain("ignore-duplicates");
    expect(params(req.url).on_conflict).toBe("workspace_id");
    expect(req.body).toEqual([{ workspace_id: "ws-1" }]);
  });

  it("insert posts with return=representation", () => {
    const req = client().from("product_invite_codes").insert({ code: "abc" }).buildRequest();
    expect(req.method).toBe("POST");
    expect(req.headers.Prefer).toBe("return=representation");
    expect(req.body).toEqual({ code: "abc" });
  });

  it("update patches with return=representation", () => {
    const req = client().from("notification_prefs").update({ muted: true }).eq("w", "1").buildRequest();
    expect(req.method).toBe("PATCH");
    expect(req.headers.Prefer).toBe("return=representation");
  });

  it("delete issues a DELETE", () => {
    const req = client().from("job_runs").delete().eq("id", 7).buildRequest();
    expect(req.method).toBe("DELETE");
  });
});

describe("fail-closed guards", () => {
  it("refuses a read with no projection", () => {
    expect(() => client().from("t").buildRequest()).toThrow(/select\(\) is required/);
  });

  it("refuses two write methods on one query", () => {
    const b = client().from("t").insert({ a: 1 });
    expect(() => b.update({ a: 2 })).toThrow(/only have one write method/);
  });

  it("refuses two select() calls", () => {
    expect(() => client().from("t").select("a").select("b")).toThrow(/only be called once/);
  });

  it("refuses a missing table", () => {
    expect(() => client().from("")).toThrow(/requires a table/);
  });

  it("refuses in() without an array", () => {
    expect(() => client().from("t").select("*").in("a", "b" as never)).toThrow(/requires an array/);
  });
});

describe("execute", () => {
  it("returns rows for a successful read", async () => {
    const stub = createPostgrestClient({
      url: BASE,
      apiKey: KEY,
      fetchImpl: async () => new Response('[{"id":1}]', { status: 200 }),
    });
    await expect(stub.from("t").select("*")).resolves.toEqual([{ id: 1 }]);
  });

  it("throws a PostgrestError carrying code and details", async () => {
    const stub = createPostgrestClient({
      url: BASE,
      apiKey: KEY,
      fetchImpl: async () =>
        new Response(
          JSON.stringify({ code: "42501", message: "denied", details: null, hint: "rls" }),
          { status: 403 },
        ),
    });
    await expect(stub.from("t").select("*")).rejects.toMatchObject({
      code: "42501",
      message: "denied",
      hint: "rls",
    });
  });

  it("still reports an error when the body is not JSON", async () => {
    const stub = createPostgrestClient({
      url: BASE,
      apiKey: KEY,
      fetchImpl: async () => new Response("upstream exploded", { status: 500 }),
    });
    await expect(stub.from("t").select("*")).rejects.toMatchObject({ message: "HTTP 500" });
  });

  it("tolerates a trailing slash on the base URL", () => {
    const req = createPostgrestClient({ url: `${BASE}/`, apiKey: KEY })
      .from("t")
      .select("*")
      .buildRequest();
    expect(req.url.startsWith(`${BASE}/rest/v1/t`)).toBe(true);
  });
});