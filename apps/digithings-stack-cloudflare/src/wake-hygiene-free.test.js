import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Pins that the daily container health check (DIG-2910) is free.
 *
 * The Mac job reads `/healthz` on graph, key and search once a day. It is only
 * worth running if that answer never boots the 6 GiB stack Container: every wake
 * bills the boot plus the whole `sleepAfter` tail, and the stack was woken all
 * night by liveness probes on 2026-10-13 (see wake-hygiene.ts).
 *
 * wake-hygiene.test.ts pins the primitives (`isHealthProbe`, `containerIsAwake`,
 * `sleepingHealthResponse`). It does not pin that the Worker uses them the way
 * it claims: move the health check below the container fetch, or read the
 * container state with something that starts it, and the primitives still pass
 * while every morning bills a boot.
 *
 * Deliberately plain `.js`, same reason as wake-readiness.test.js: tsconfig
 * scopes `types` to @cloudflare/workers-types only, and index.ts imports
 * `cloudflare:workers` / `@cloudflare/containers`, so it cannot be imported
 * under plain vitest.
 */
const here = dirname(fileURLToPath(import.meta.url));

function stackSource() {
  return readFileSync(join(here, "index.ts"), "utf-8");
}

/** The health-probe branch, from the check to the end of its block. */
function healthBlock(source) {
  const start = source.indexOf("if (isHealthProbe(request, url.pathname)) {");
  expect(start).toBeGreaterThan(-1);
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error("the health branch is never closed");
}

describe("the daily health check is free", () => {
  it("answers a sleeping container with the Worker", () => {
    const block = healthBlock(stackSource());
    expect(block).toContain("containerIsAwake(status)");
    expect(block).toContain("sleepingHealthResponse(request)");
  });

  it("never fetches the container for a health probe", () => {
    const block = healthBlock(stackSource());
    expect(block).not.toContain("container.fetch");
    expect(block).not.toContain(".start(");
  });

  it("reads the container state without waking it", () => {
    const block = healthBlock(stackSource());
    expect(block).toContain("getState()");
  });

  it("answers the probe before the container proxy runs", () => {
    const source = stackSource();
    const proxy = source.indexOf("container.fetch(switchPort(request.clone(), port))");
    expect(proxy).toBeGreaterThan(-1);
    expect(proxy).toBeGreaterThan(source.indexOf("if (isHealthProbe(request, url.pathname)) {"));
  });

  it("answers the worker only status probe before the container routes", () => {
    const source = stackSource();
    const status = source.indexOf('if (url.pathname === "/_stack/status")');
    const containerRoutes = source.indexOf(
      'runIsolated("container-routes", () => import("./ports"), async ({ portForHostname })',
    );
    expect(status).toBeGreaterThan(-1);
    expect(containerRoutes).toBeGreaterThan(status);
    expect(source.slice(status, containerRoutes)).toContain("getStackStatus()");
  });
});
