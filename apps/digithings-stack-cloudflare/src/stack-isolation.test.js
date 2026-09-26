import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getStackStatus,
  resetStackModuleHealth,
  runIsolated,
  warnStackModule,
} from "./route-modules";

/**
 * Fault isolation for the single-worker fold skeleton (#4685).
 *
 * Behavioral tests drive `runIsolated` (the same helper every fetch() route
 * group is wired through) with injected loaders: a throwing loader is the
 * fault-injection seam — no real module is broken. Source-text pins below
 * prove index.ts wires each group through that helper with a lazy import().
 *
 * Deliberately plain `.js`, same reason as the other pin tests: tsconfig
 * scopes `types` to @cloudflare/workers-types only, so node:fs / node:path /
 * node:url have no ambient declarations in a `.ts` file here.
 */

const here = dirname(fileURLToPath(import.meta.url));

afterEach(() => {
  resetStackModuleHealth();
  vi.restoreAllMocks();
});

function ok(text = "ok") {
  return new Response(text, { status: 200 });
}

describe("runIsolated", () => {
  it("passes a healthy module's response through and marks it loaded", async () => {
    const res = await runIsolated("key-proxy", async () => ({}), async () => ok());
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
    const status = getStackStatus();
    expect(status.modules["key-proxy"]).toEqual({ state: "loaded", lastError: null });
  });

  it("a failing loader degrades ONLY its own group with a 503", async () => {
    const marketRes = await runIsolated(
      "market-data",
      async () => {
        throw new Error("hyparquet exploded");
      },
      async () => ok(),
    );
    expect(marketRes.status).toBe(503);
    expect(await marketRes.text()).toContain("market-data unavailable");

    // Sibling groups still serve: a healthy loader passes through untouched.
    const keyRes = await runIsolated("key-proxy", async () => ({}), async () => ok());
    expect(keyRes.status).toBe(200);

    const status = getStackStatus();
    expect(status.modules["market-data"]).toEqual({
      state: "degraded",
      lastError: "hyparquet exploded",
    });
    expect(status.modules["key-proxy"]).toEqual({ state: "loaded", lastError: null });
    expect(status.modules["mcp-edge"]).toEqual({ state: "unloaded", lastError: null });
    expect(status.modules["container-routes"]).toEqual({
      state: "unloaded",
      lastError: null,
    });
  });

  it("a throwing route handler degrades its own group with a 503", async () => {
    const res = await runIsolated(
      "mcp-edge",
      async () => ({}),
      async () => {
        throw new Error("container edge blew up");
      },
    );
    expect(res.status).toBe(503);
    expect(await res.text()).toContain("mcp-edge unavailable");
    expect(getStackStatus().modules["mcp-edge"]).toEqual({
      state: "degraded",
      lastError: "container edge blew up",
    });
  });

  it("a later success heals a degraded group and clears lastError", async () => {
    await runIsolated("market-data", async () => {
      throw new Error("transient");
    }, async () => ok());
    expect(getStackStatus().modules["market-data"].state).toBe("degraded");

    const res = await runIsolated("market-data", async () => ({}), async () => ok());
    expect(res.status).toBe(200);
    expect(getStackStatus().modules["market-data"]).toEqual({
      state: "loaded",
      lastError: null,
    });
  });

  it("stringifies non-Error failures instead of crashing", async () => {
    const res = await runIsolated("container-routes", async () => {
      // eslint-disable-next-line no-throw-literal
      throw "plain string failure";
    }, async () => ok());
    expect(res.status).toBe(503);
    expect(getStackStatus().modules["container-routes"].lastError).toBe(
      "plain string failure",
    );
  });
});

describe("warning sink", () => {
  it("logs a structured JSON warning with module, event, and message only", async () => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
    warnStackModule("market-data", "module-load-failed", new Error("boom"));
    expect(spy).toHaveBeenCalledTimes(1);
    const parsed = JSON.parse(spy.mock.calls[0][0]);
    expect(parsed).toMatchObject({
      level: "warn",
      scope: "digithings-stack",
      module: "market-data",
      event: "module-load-failed",
      error: "boom",
    });
    expect(Object.keys(parsed).sort()).toEqual(
      ["error", "event", "level", "module", "scope"].sort(),
    );
  });

  it("emits a warning on both load and route failures", async () => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {});
    await runIsolated("market-data", async () => {
      throw new Error("load");
    }, async () => ok());
    await runIsolated("mcp-edge", async () => ({}), async () => {
      throw new Error("route");
    });
    const events = spy.mock.calls.map((call) => JSON.parse(call[0]).event);
    expect(events).toEqual(["module-load-failed", "route-failed"]);
  });

  it("never throws, even if console.warn itself throws", () => {
    const spy = vi.spyOn(console, "warn").mockImplementation(() => {
      throw new Error("logger down");
    });
    expect(() => warnStackModule("key-proxy", "route-failed", new Error("x"))).not.toThrow();
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("getStackStatus", () => {
  it("reports all four groups as unloaded before any traffic", () => {
    expect(getStackStatus()).toEqual({
      ok: true,
      service: "digithings-stack",
      modules: {
        "key-proxy": { state: "unloaded", lastError: null },
        "mcp-edge": { state: "unloaded", lastError: null },
        "market-data": { state: "unloaded", lastError: null },
        "container-routes": { state: "unloaded", lastError: null },
      },
    });
  });

  it("reflects a degraded group after a failure", async () => {
    await runIsolated("mcp-edge", async () => {
      throw new Error("mcp ports unreachable");
    }, async () => ok());
    const status = getStackStatus();
    expect(status.ok).toBe(true);
    expect(status.modules["mcp-edge"].state).toBe("degraded");
    expect(status.modules["mcp-edge"].lastError).toBe("mcp ports unreachable");
  });

  it("returns copies, never live internal refs", async () => {
    await runIsolated("key-proxy", async () => ({}), async () => ok());
    const first = getStackStatus();
    first.modules["key-proxy"].state = "degraded";
    expect(getStackStatus().modules["key-proxy"].state).toBe("loaded");
  });
});

describe("index.ts isolation wiring", () => {
  const source = readFileSync(join(here, "index.ts"), "utf-8");

  it("serves GET /_stack/status from the health snapshot, without module loads", () => {
    expect(source).toContain('if (url.pathname === "/_stack/status")');
    expect(source).toContain("Response.json(getStackStatus())");
  });

  it("lazy-loads one module per route group behind runIsolated", () => {
    expect(source).toContain('runIsolated("key-proxy", () => import("./ports")');
    expect(source).toContain('runIsolated("mcp-edge", () => import("./ports")');
    expect(source).toContain(
      'runIsolated("market-data", () => import("./market-data")',
    );
    expect(source).toContain('runIsolated("container-routes", () => import("./ports")');
  });

  it("no longer eagerly imports the market-data handler at the top level", () => {
    expect(source).not.toContain('from "./market-data"');
    expect(source).not.toContain("import { handleMarketData }");
  });

  it("keeps the MCP edge path fail-closed and synchronous (401 before isolation)", () => {
    const mcpStart = source.indexOf("MCP_EDGE_PREFIX}/`)");
    expect(mcpStart).toBeGreaterThan(-1);
    const authCheck = source.indexOf(
      "if (!expected || !provided || provided !== expected)",
    );
    const isolated = source.indexOf('runIsolated("mcp-edge"');
    expect(authCheck).toBeGreaterThan(mcpStart);
    expect(isolated).toBeGreaterThan(authCheck);
  });
});
