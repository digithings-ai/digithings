import { afterEach, describe, expect, it } from "vitest";
import app, { type Env } from "./index";
import { ROUTE_MODULES, userIdFor } from "./routes";
import { Registry, matchPath } from "./routes/registry";
import { corsHeaders } from "./cors";

const ORIGIN = "https://digiquant.io";
const ENV: Env = { DASHBOARD_DEV_CALLER: "enterprise+12x" };
const FREE: Env = {};

afterEach(() => {
  ROUTE_MODULES.length = 0;
});

function install(): void {
  ROUTE_MODULES.push((reg) => {
    reg.get("/fx/pairs/{pair}/path", async (_req, ctx) => Response.json({ pair: ctx.params.pair, user: ctx.userId }));
    reg.get("/fx/summary", async () => Response.json({ exact: true }));
    reg.add("PUT", "/fx/directives", async (req, ctx) => Response.json({ user: ctx.userId, body: await req.json() }));
    reg.add("DELETE", "/not/in/catalog", async () => Response.json({ ok: true }));
  });
}

const put = (headers: Record<string, string> = {}, path = "/fx/directives") =>
  new Request(`https://x${path}`, { method: "PUT", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify({ a: 1 }) });

describe("registry", () => {
  it("matchPath fills params and rejects shape mismatches", () => {
    expect(matchPath("/fx/pairs/{pair}/path", "/fx/pairs/EURUSD/path")).toEqual({ pair: "EURUSD" });
    expect(matchPath("/fx/pairs/{pair}/path", "/fx/pairs//path")).toBeNull();
    expect(matchPath("/fx/pairs/{pair}/path", "/fx/pairs/EURUSD")).toBeNull();
    expect(matchPath("/a/{x}", "/a/%E0%A4%A")).toBeNull();
  });
  it("exact beats template; duplicates throw", () => {
    const r = new Registry<null>();
    r.get("/a/{x}", async () => new Response("t"));
    r.get("/a/b", async () => new Response("e"));
    expect(r.match("GET", "/a/b")!.params).toEqual({});
    expect(r.match("GET", "/a/c")!.params).toEqual({ x: "c" });
    expect(r.match("PUT", "/a/c")).toBeNull();
    expect(() => r.get("/a/b", async () => new Response())).toThrow(/duplicate/);
  });
});

describe("GET via registry", () => {
  it("serves template routes for unknown paths, behind the gate", async () => {
    install();
    const ok = await app.fetch(new Request("https://x/fx/pairs/EURUSD/path"), ENV);
    expect(ok.status).toBe(200);
    expect(await ok.json()).toEqual({ pair: "EURUSD", user: null });
    expect((await app.fetch(new Request("https://x/fx/pairs/EURUSD/path"), FREE)).status).toBe(403);
  });
  it("unregistered paths still fall through to the unknown-route error", async () => {
    const res = await app.fetch(new Request("https://x/fx/pairs/EURUSD/path"), ENV);
    expect(res.status).toBe(400);
  });
});

describe("writes", () => {
  it("unregistered write is rejected before anything runs", async () => {
    expect((await app.fetch(put({ "x-digi-user": "u1" }), ENV)).status).toBe(400);
  });
  it("401 unauthorized without a verified user", async () => {
    install();
    const res = await app.fetch(put(), ENV);
    expect(res.status).toBe(401);
    expect(((await res.json()) as { error: { code: string } }).error.code).toBe("unauthorized");
    expect((await app.fetch(put({ "x-digi-user": "bad user!" }), ENV)).status).toBe(401);
  });
  it("403 when the catalog does not grant the route to the caller", async () => {
    install();
    const res = await app.fetch(put({ "x-digi-user": "u1" }), FREE);
    expect(res.status).toBe(403);
  });
  it("write paths outside the catalog fail closed", async () => {
    install();
    const res = await app.fetch(new Request("https://x/not/in/catalog", { method: "DELETE", headers: { "x-digi-user": "u1" } }), ENV);
    expect(res.status).toBe(403);
  });
  it("runs the handler for a verified user on a granted route", async () => {
    install();
    const res = await app.fetch(put({ "x-digi-user": "u1" }), ENV);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ user: "u1", body: { a: 1 } });
  });
  it("maps UpstreamError from a handler to 502 upstream_empty", async () => {
    const { UpstreamError } = await import("./supabase");
    ROUTE_MODULES.push((reg) => reg.add("PUT", "/fx/directives", async () => { throw new UpstreamError("boom", 500, ""); }));
    const res = await app.fetch(put({ "x-digi-user": "u1" }), ENV);
    expect(res.status).toBe(502);
  });
  it("userIdFor trims and bounds", () => {
    expect(userIdFor(new Request("https://x", { headers: { "x-digi-user": " abc-123 " } }))).toBe("abc-123");
    expect(userIdFor(new Request("https://x", { headers: { "x-digi-user": "a".repeat(129) } }))).toBeNull();
    expect(userIdFor(new Request("https://x"))).toBeNull();
  });
});

describe("CORS for writes", () => {
  it("allows write methods and identity headers", () => {
    const h = corsHeaders(ORIGIN, [ORIGIN]);
    const methods = h["Access-Control-Allow-Methods"]!.split(",").map((m) => m.trim());
    expect(methods).toEqual(expect.arrayContaining(["GET", "PUT", "POST", "DELETE", "OPTIONS"]));
    expect(h["Access-Control-Allow-Headers"]!.toLowerCase()).toContain("x-digi-user");
    expect(h["Access-Control-Allow-Headers"]!.toLowerCase()).toContain("content-type");
  });
  it("write responses carry CORS", async () => {
    install();
    const res = await app.fetch(new Request("https://x/fx/directives", { method: "PUT", headers: { origin: ORIGIN } }), ENV);
    expect(res.status).toBe(401);
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe(ORIGIN);
  });
});
