/**
 * One policy, two doors: the HTTP routes and the MCP tools both gate on the
 * caller's access manifest (access.ts). Identity = edge headers.
 */
import { describe, expect, it } from "vitest";
import app, { type Env } from "./index";
import { callerFor, routeMatches, routeVerdict, buildManifest } from "./access";

const KEY = "k";
const ENV: Env = { MCP_EDGE_KEY: KEY };

const get = (path: string, h: Record<string, string> = {}) => app.fetch(new Request(`https://x${path}`, { headers: h }), ENV);
const rpc = (body: unknown, h: Record<string, string> = {}) =>
  app.fetch(new Request("https://x/mcp", { method: "POST", headers: { "x-digi-mcp-key": KEY, ...h }, body: JSON.stringify(body) }), ENV);
const names = async (h: Record<string, string>) => {
  const j = (await (await rpc({ jsonrpc: "2.0", id: 1, method: "tools/list" }, h)).json()) as { result: { tools: { name: string }[] } };
  return j.result.tools.map((t) => t.name);
};

describe("HTTP gate", () => {
  it("free caller: open routes serve, pro routes are 403 forbidden", async () => {
    expect((await get("/brief")).status).toBe(200);
    const res = await get("/performance");
    expect(res.status).toBe(403);
    expect(((await res.json()) as { error: { code: string } }).error.code).toBe("forbidden");
  });
  it("pro caller reaches pro routes", async () => {
    expect((await get("/performance", { "x-digi-tier": "pro" })).status).toBe(200);
  });
  it("healthz and the manifest stay open", async () => {
    expect((await get("/healthz")).status).toBe(200);
    expect((await get("/access/manifest")).status).toBe(200);
  });
});

describe("MCP gate", () => {
  it("free caller sees only granted tools; pro sees more", async () => {
    const free = await names({});
    expect(free).toContain("get_brief");
    expect(free).toContain("get_access_manifest");
    expect(free).not.toContain("get_performance");
    expect(await names({ "x-digi-tier": "pro" })).toContain("get_performance");
  });
  it("calling a withheld tool is refused, not served", async () => {
    const res = await rpc({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "get_performance", arguments: {} } });
    const j = (await res.json()) as { error?: { code: number; message: string } };
    expect(j.error?.code).toBe(-32003);
  });
  it("the key is still required", async () => {
    const res = await app.fetch(new Request("https://x/mcp", { method: "POST", body: "{}" }), ENV);
    expect(res.status).toBe(401);
  });
});

describe("helpers", () => {
  it("template routes match one segment", () => {
    expect(routeMatches("/fx/pairs/{pair}/path", "/fx/pairs/USDJPY/path")).toBe(true);
    expect(routeMatches("/fx/pairs/{pair}/path", "/fx/pairs/path")).toBe(false);
  });
  it("fx routes are forbidden without the 12x group", () => {
    expect(routeVerdict(buildManifest({ tier: "max", groups: [] }), "/fx/summary")).toBe("forbidden");
    expect(routeVerdict(buildManifest({ tier: "free", groups: ["12x"] }), "/fx/summary")).toBe("allowed");
    expect(routeVerdict(buildManifest({ tier: "free", groups: [] }), "/v1/tables/x")).toBe("ungoverned");
  });
  it("dev caller applies only when no identity headers are sent", () => {
    const env = { DASHBOARD_DEV_CALLER: "max+12x" };
    expect(callerFor(new Request("https://x/"), env)).toEqual({ tier: "max", groups: ["12x"] });
    expect(callerFor(new Request("https://x/", { headers: { "x-digi-tier": "free" } }), env)).toEqual({ tier: "free", groups: [] });
    expect(callerFor(new Request("https://x/"), {})).toEqual({ tier: "free", groups: [] });
  });
});
