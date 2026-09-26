/**
 * Per-module fault isolation for the digithings-stack edge Worker (#4685).
 *
 * Skeleton for the single-worker fold: each fetch() route group (key proxy,
 * in-container MCP edge servers, R2 market data, container hostnames) loads
 * its handler module through `runIsolated`, which pairs a lazy `import()` with
 * a per-route try/catch. A failing module returns 503 for its own paths only;
 * every other group keeps serving.
 *
 * Health model per group: `unloaded` (no request yet) → `loaded` (last
 * handling succeeded) / `degraded` (last handling failed, with `lastError`).
 * A later success heals the entry back to `loaded` and clears `lastError`, so
 * a transient blip does not pin the status surface forever. Load AND route
 * failures both degrade: from the caller's side either one means "this group's
 * paths are down", and the distinction is preserved in the warning event name.
 *
 * The warning sink is `console.warn` with a single JSON line (picked up by
 * Workers Logs; observability is enabled in wrangler.toml). It carries the
 * module name, the event, and the error message only — never env values, keys,
 * or request bodies. Logging itself is guarded so it can never throw across
 * groups.
 *
 * `GET /_stack/status` (wired in index.ts) serves `getStackStatus()` directly:
 * it touches no module loader, so it stays up even when every group is
 * degraded. Same for `/_stack/meta`.
 *
 * Test seam: `runIsolated` takes the importer as a parameter, so tests inject
 * a throwing loader (fault injection) instead of breaking a real module. This
 * file has no platform imports (`cloudflare:workers`, `@cloudflare/containers`)
 * precisely so vitest can import it under node.
 */

/** Route groups with independent failure budgets. */
export type StackModuleName =
  | "key-proxy"
  | "mcp-edge"
  | "market-data"
  | "container-routes";

export type StackModuleState = "unloaded" | "loaded" | "degraded";

export interface StackModuleHealth {
  state: StackModuleState;
  lastError: string | null;
}

export interface StackStatus {
  ok: true;
  service: "digithings-stack";
  modules: Record<StackModuleName, StackModuleHealth>;
}

const MODULE_NAMES: StackModuleName[] = [
  "key-proxy",
  "mcp-edge",
  "market-data",
  "container-routes",
];

function freshHealth(): Record<StackModuleName, StackModuleHealth> {
  return {
    "key-proxy": { state: "unloaded", lastError: null },
    "mcp-edge": { state: "unloaded", lastError: null },
    "market-data": { state: "unloaded", lastError: null },
    "container-routes": { state: "unloaded", lastError: null },
  };
}

/** Module-scoped registry (Worker isolate global; survives across requests). */
const health: Record<StackModuleName, StackModuleHealth> = freshHealth();

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Structured warning sink. Single JSON line via console.warn; never throws,
 * never carries secrets (message text only).
 */
export function warnStackModule(
  module: StackModuleName,
  event: "module-load-failed" | "route-failed",
  error: unknown,
): void {
  try {
    console.warn(
      JSON.stringify({
        level: "warn",
        scope: "digithings-stack",
        module,
        event,
        error: errorMessage(error),
      }),
    );
  } catch {
    // Logging must never throw across route groups.
  }
}

/**
 * Run one route group's lazy import + handler with per-group isolation.
 *
 * - `load` is the group's lazy `import()` (the fault-injection seam: tests
 *   pass a throwing loader; prod passes the real dynamic import).
 * - Import failure → warn (`module-load-failed`), mark degraded, 503.
 * - Handler failure → warn (`route-failed`), mark degraded, 503.
 * - Success → mark loaded, clear `lastError`, return the handler response.
 *
 * Only this group's paths are affected; every other group keeps serving.
 */
export async function runIsolated<T>(
  module: StackModuleName,
  load: () => Promise<T>,
  route: (mod: T) => Promise<Response>,
): Promise<Response> {
  let mod: T;
  try {
    mod = await load();
  } catch (error) {
    health[module] = { state: "degraded", lastError: errorMessage(error) };
    warnStackModule(module, "module-load-failed", error);
    return moduleUnavailable(module, error);
  }
  try {
    const response = await route(mod);
    health[module] = { state: "loaded", lastError: null };
    return response;
  } catch (error) {
    health[module] = { state: "degraded", lastError: errorMessage(error) };
    warnStackModule(module, "route-failed", error);
    return moduleUnavailable(module, error);
  }
}

function moduleUnavailable(module: StackModuleName, error: unknown): Response {
  return new Response(
    `digithings-stack: ${module} unavailable: ${errorMessage(error)}`,
    { status: 503 },
  );
}

/** Snapshot for `GET /_stack/status`. Returns copies; never internal refs. */
export function getStackStatus(): StackStatus {
  return {
    ok: true,
    service: "digithings-stack",
    modules: {
      "key-proxy": { ...health["key-proxy"] },
      "mcp-edge": { ...health["mcp-edge"] },
      "market-data": { ...health["market-data"] },
      "container-routes": { ...health["container-routes"] },
    },
  };
}

/** Reset the registry (tests only). */
export function resetStackModuleHealth(): void {
  for (const name of MODULE_NAMES) {
    health[name] = { state: "unloaded", lastError: null };
  }
}
