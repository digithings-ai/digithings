/**
 * One policy, two doors: the HTTP routes and the MCP tools both gate on the
 * caller's access manifest (access.ts). Identity = edge headers.
 */
import { describe, expect, it } from "vitest";
import app, { type Env } from "./index";
import { callerFor, routeMatches, routeVerdict, buildManifest } from "./access";

const KEY = "k";
const ENV: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1", MCP_EDGE_KEY: KEY };

const get = (path: string, h: Record<string, string> = {}) => app.fetch(new Request(`https://x${path}`, { headers: h }), ENV);
const rpc = (body: unknown, h: Record<string, string> = {}) =>
  app.fetch(new Request("https://x/mcp", { method: "POST", headers: { "x-digi-mcp-key": KEY, ...h }, body: JSON.stringify(body) }), ENV);
const names = async (h: Record<string, string>) => {
  const j = (await (await rpc({ jsonrpc: "2.0", id: 1, method: "tools/list" }, h)).json()) as { result: { tools: { name: string }[] } };
  return j.result.tools.map((t) => t.name);
};

const FREE = { "x-digi-tier": "free" };

describe("HTTP gate", () => {
  it("free caller: open routes serve, brief routes are 403 forbidden", async () => {
    expect((await get("/brief", FREE)).status).toBe(200);
    const res = await get("/performance", FREE);
    expect(res.status).toBe(403);
    expect(((await res.json()) as { error: { code: string } }).error.code).toBe("forbidden");
  });
  it("secretless anonymous caller gets the stub lane, not a free-tier 403", async () => {
    expect((await get("/performance")).status).toBe(200);
    const tables = await get("/v1/tables/positions?select=*");
    expect(tables.status).toBe(502);
    expect(((await tables.json()) as { error: { code: string } }).error.code).toBe("upstream_empty");
  });
  it("brief caller reaches brief routes", async () => {
    expect((await get("/performance", { "x-digi-tier": "brief" })).status).toBe(200);
  });
  it("healthz and the manifest stay open", async () => {
    expect((await get("/healthz")).status).toBe(200);
    expect((await get("/access/manifest")).status).toBe(200);
  });
});

describe("MCP gate", () => {
  it("free caller sees only granted tools; brief sees more", async () => {
    const free = await names(FREE);
    expect(free).toContain("get_brief");
    expect(free).toContain("get_access_manifest");
    expect(free).not.toContain("get_performance");
    const stub = await names({});
    expect(stub).toEqual([
      "get_portfolio",
      "get_allocations",
      "get_nav_series",
      "get_brief",
      "get_performance",
      "get_kpis_live",
      "get_benchmarks",
      "get_ledger",
    ]);
    expect(await names({ "x-digi-tier": "brief" })).toContain("get_performance");
  });
  it("calling a withheld tool is refused, not served", async () => {
    const res = await rpc({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "get_performance", arguments: {} } }, FREE);
    const j = (await res.json()) as { error?: { code: number; message: string } };
    expect(j.error?.code).toBe(-32003);
  });
  it("the key is still required", async () => {
    const res = await app.fetch(new Request("https://x/mcp", { method: "POST", body: "{}" }), ENV);
    expect(res.status).toBe(401);
  });
});

describe("edge identity key", () => {
  const E: Env = { DASHBOARD_TRUST_IDENTITY_HEADERS: "1", MCP_EDGE_KEY: KEY, DASHBOARD_EDGE_KEY: "edge" };
  const call = (h: Record<string, string>) => app.fetch(new Request("https://x/performance", { headers: h }), E);
  it("ignores identity headers without the edge key (falls to free)", async () => {
    expect((await call({ "x-digi-tier": "enterprise" })).status).toBe(403);
  });
  it("honours them with the edge key", async () => {
    expect((await call({ "x-digi-tier": "brief", "x-digi-edge-key": "edge" })).status).toBe(200);
  });
});

describe("raw tables are brief+", () => {
  it("free caller is 403", async () => {
    expect((await get("/v1/tables/positions?select=*", FREE)).status).toBe(403);
  });
});

describe("helpers", () => {
  it("template routes match one segment", () => {
    expect(routeMatches("/fx/pairs/{pair}/path", "/fx/pairs/USDJPY/path")).toBe(true);
    expect(routeMatches("/fx/pairs/{pair}/path", "/fx/pairs/path")).toBe(false);
  });
  it("fx routes are forbidden without the 12x group", () => {
    expect(routeVerdict(buildManifest({ tier: "enterprise", groups: [] }), "/fx/summary")).toBe("forbidden");
    expect(routeVerdict(buildManifest({ tier: "free", groups: ["12x"] }), "/fx/summary")).toBe("allowed");
    expect(routeVerdict(buildManifest({ tier: "free", groups: [] }), "/v1/tables/x")).toBe("ungoverned");
  });
  it("dev caller applies only when no identity headers are sent", () => {
    const env = { DASHBOARD_DEV_CALLER: "enterprise+12x", DASHBOARD_TRUST_IDENTITY_HEADERS: "1" };
    expect(callerFor(new Request("https://x/"), env)).toEqual({ tier: "enterprise", groups: ["12x"] });
    expect(callerFor(new Request("https://x/", { headers: { "x-digi-tier": "free" } }), env)).toEqual({ tier: "free", groups: [] });
    expect(callerFor(new Request("https://x/"), {})).toEqual({ tier: "free", groups: [] });
  });
  it("identity headers fail closed when no edge key is configured", () => {
    const spoof = new Request("https://x/", { headers: { "x-digi-tier": "enterprise", "x-digi-groups": "12x" } });
    expect(callerFor(spoof, {})).toEqual({ tier: "free", groups: [] });
    expect(callerFor(spoof, { DASHBOARD_EDGE_KEY: "edge" })).toEqual({ tier: "free", groups: [] });
  });
});
