import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  DASHBOARD_API_PREFIX,
  DASHBOARD_MCP_TOOLS,
  handleDashboardApi,
  isDashboardApiPath,
  stripDashboardApiPrefix,
} from "./dashboard-api";

/**
 * Folded dashboard-api mount (slice 2, #4687).
 *
 * Behavioral tests drive `handleDashboardApi` (the same adapter index.ts
 * lazy-loads behind `runIsolated("dashboard-api", ...)`) over the stub lane
 * (no secrets, no network): prefix stripping, the §1 envelope, the
 * exact-match CORS allowlist, and the 8 MCP tools through the one shared
 * dispatch. Source-text pins prove the adapter reuses the standalone
 * worker's code instead of reimplementing routes.
 *
 * Deliberately plain `.js`, same reason as stack-isolation.test.js:
 * tsconfig scopes `types` to @cloudflare/workers-types only.
 */

const here = dirname(fileURLToPath(import.meta.url));

const STUB_ENV = {};
const MCP_ENV = { MCP_EDGE_KEY: "test-edge-key" };

function req(path, init = {}) {
  return new Request(`https://stack.test${path}`, init);
}

async function mounted(path, env = STUB_ENV, init = {}) {
  const request = req(path, init);
  return handleDashboardApi(request, env, new URL(request.url));
}

describe("prefix routing", () => {
  it("matches the canonical module path exactly or as a prefix", () => {
    expect(DASHBOARD_API_PREFIX).toBe("/dashboard-api");
    expect(isDashboardApiPath("/dashboard-api")).toBe(true);
    expect(isDashboardApiPath("/dashboard-api/portfolio")).toBe(true);
    expect(isDashboardApiPath("/dashboard-api/v1/tables/positions")).toBe(true);
    expect(isDashboardApiPath("/dashboard-api-other")).toBe(false);
    expect(isDashboardApiPath("/_stack/mcp/zammad/mcp")).toBe(false);
    expect(isDashboardApiPath("/v1/market/tickers")).toBe(false);
  });

  it("strips the prefix, mapping the bare prefix to /", () => {
    expect(stripDashboardApiPrefix("/dashboard-api")).toBe("/");
    expect(stripDashboardApiPrefix("/dashboard-api/portfolio")).toBe("/portfolio");
    expect(stripDashboardApiPrefix("/dashboard-api/kpis/live")).toBe("/kpis/live");
    expect(stripDashboardApiPrefix("/dashboard-api/v1/tables/positions")).toBe(
      "/v1/tables/positions",
    );
  });
});

describe("folded routes (stub lane)", () => {
  it("serves the contracted routes under /dashboard-api/* with the §1 envelope", async () => {
    const cases = [
      ["/dashboard-api/portfolio", "invested"],
      ["/dashboard-api/allocations", "rows"],
      ["/dashboard-api/nav-series", "points"],
      ["/dashboard-api/brief?overlay=off", "book_as_of"],
      ["/dashboard-api/performance", "nav"],
      ["/dashboard-api/kpis/live", "universe"],
      ["/dashboard-api/benchmarks?tickers=SPY", "universe"],
      ["/dashboard-api/ledger", "events"],
    ];
    for (const [path, dataKey] of cases) {
      const res = await mounted(path);
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body).toHaveProperty("data");
      expect(body).toHaveProperty("as_of");
      expect(body).toHaveProperty("retrieval_pin");
      expect(body).toHaveProperty("provenance");
      expect(body.data).toHaveProperty(dataKey);
    }
  });

  it("keeps /healthz and the unknown-route 400 envelope through the fold", async () => {
    const health = await mounted("/dashboard-api/healthz");
    expect(health.status).toBe(200);
    expect(await health.json()).toEqual({ ok: true, service: "dashboard-api" });

    const unknown = await mounted("/dashboard-api/nope");
    expect(unknown.status).toBe(400);
  });

  it("fail-closes /v1/tables/* without Supabase env (502 upstream_empty)", async () => {
    const res = await mounted("/dashboard-api/v1/tables/positions?select=*&limit=1");
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.error.code).toBe("upstream_empty");
  });
});

describe("CORS through the fold", () => {
  it("echoes an allowlisted origin and always sets Vary: Origin", async () => {
    const res = await mounted("/dashboard-api/portfolio", STUB_ENV, {
      headers: { Origin: "https://digiquant.io" },
    });
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe("https://digiquant.io");
    expect(res.headers.get("Vary")).toBe("Origin");
  });

  it("sends no ACAO for a non-allowlisted origin (Vary still attached)", async () => {
    const res = await mounted("/dashboard-api/portfolio", STUB_ENV, {
      headers: { Origin: "https://evil.example" },
    });
    expect(res.headers.get("Access-Control-Allow-Origin")).toBeNull();
    expect(res.headers.get("Vary")).toBe("Origin");
  });

  it("short-circuits OPTIONS preflights with 204 and an empty body", async () => {
    const res = await mounted("/dashboard-api/portfolio", STUB_ENV, {
      method: "OPTIONS",
      headers: { Origin: "https://digithings.ai" },
    });
    expect(res.status).toBe(204);
    expect(await res.text()).toBe("");
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe("https://digithings.ai");
  });
});

describe("folded MCP tools (one shared dispatch)", () => {
  function mcp(body, env = MCP_ENV, headers = {}) {
    return mounted("/dashboard-api/mcp", env, {
      method: "POST",
      headers: { "content-type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
  }

  const authed = { "x-digi-mcp-key": "test-edge-key" };

  it("exposes exactly the standalone worker's 8 tools (same tools)", async () => {
    expect(DASHBOARD_MCP_TOOLS).toHaveLength(8);
    const listed = { jsonrpc: "2.0", id: 1, method: "tools/list" };
    const res = await mcp(listed, MCP_ENV, authed);
    expect(res.status).toBe(200);
    const body = await res.json();
    const names = body.result.tools.map((t) => t.name);
    expect(names).toEqual(DASHBOARD_MCP_TOOLS.map((t) => t.name));
    expect(names).toEqual([
      "get_portfolio",
      "get_allocations",
      "get_nav_series",
      "get_brief",
      "get_performance",
      "get_kpis_live",
      "get_benchmarks",
      "get_ledger",
    ]);
  });

  it("runs tools/call through the shared route dispatch (byte-identical)", async () => {
    const viaHttp = await (await mounted("/dashboard-api/portfolio")).text();
    const call = {
      jsonrpc: "2.0",
      id: 2,
      method: "tools/call",
      params: { name: "get_portfolio", arguments: {} },
    };
    const viaMcp = await mcp(call, MCP_ENV, authed);
    const body = await viaMcp.json();
    expect(body.result.isError).toBe(false);
    expect(body.result.content[0].text).toBe(viaHttp);
  });

  it("fail-closes without the edge key (401, no envelope)", async () => {
    const res = await mcp({ jsonrpc: "2.0", id: 3, method: "tools/list" }, MCP_ENV);
    expect(res.status).toBe(401);
    const resNoSecret = await mcp(
      { jsonrpc: "2.0", id: 4, method: "tools/list" },
      STUB_ENV,
      authed,
    );
    expect(resNoSecret.status).toBe(401);
  });
});

describe("adapter source pins", () => {
  const source = readFileSync(join(here, "dashboard-api.ts"), "utf-8");

  it("forwards to the standalone worker entry instead of reimplementing routes", () => {
    expect(source).toContain('from "../../dashboard-api/src/index"');
    expect(source).toContain('from "../../dashboard-api/src/mcp"');
    expect(source).not.toContain("mountEnvelopeRoutes");
    expect(source).not.toContain("registerBriefRoutes");
    expect(source).not.toContain("tryHandleLedger");
    expect(source).not.toContain("tryHandleTables");
  });

  it("applies no own CORS logic (the standalone worker's code owns the allowlist)", () => {
    expect(source).not.toContain("Access-Control-Allow-Origin");
    expect(source).not.toContain("resolveAllowlist");
    expect(source).not.toContain("corsHeaders");
  });
});
