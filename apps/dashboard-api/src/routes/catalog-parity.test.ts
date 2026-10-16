import { describe, expect, it } from "vitest";
import { governedRoutes } from "../access";
import { buildRegistry } from "./index";

/**
 * Catalog-registry parity (DIG-2804).
 *
 * Every data route the access catalog governs must resolve to a handler:
 * either a legacy envelope route in `index.ts`, the generic tables route,
 * or a registry entry. Otherwise the dispatcher falls through to
 * `unknown route` (400) for a route the sidebar claims is granted.
 */

// GET paths served outside the domain registry.
const LEGACY_GET = new Set([
  "/portfolio",
  "/allocations",
  "/nav-series",
  "/brief",
  "/performance",
  "/kpis/live",
  "/benchmarks",
  "/ledger",
  "/access/manifest",
  "/healthz",
]);

function resolves(path: string): boolean {
  const base = path.split("?")[0]!;
  if (LEGACY_GET.has(base)) return true;
  if (base.startsWith("/v1/tables/")) return true;
  return buildRegistry().match("GET", base) !== null;
}

describe("catalog-registry parity", () => {
  it("every governed catalog route resolves to a GET handler", () => {
    const routes = governedRoutes();
    expect(routes.length).toBeGreaterThan(40);
    const missing = routes.filter((r) => !resolves(r));
    expect(missing).toEqual([]);
  });

  it("every registry GET route is governed or legacy (no ungoverned reads)", () => {
    const reg = buildRegistry().list().filter((e) => e.method === "GET");
    expect(reg.length).toBeGreaterThan(40);
    const governed = new Set(governedRoutes().map((r) => r.split("?")[0]!));
    const stray = reg
      .map((e) => e.path)
      .filter((p) => !LEGACY_GET.has(p) && !p.startsWith("/v1/tables/") && !governed.has(p));
    expect(stray).toEqual([]);
  });
});
