/**
 * dashboard-api fold (slice 2, #4687): mount the standalone dashboard-api
 * worker's routes under the canonical module path `/dashboard-api/*` inside
 * the digithings-stack worker.
 *
 * Same handlers, one dispatch: requests are prefix-stripped and forwarded to
 * the dashboard-api worker entry (`../../dashboard-api/src/index.ts`), whose
 * own fetch applies its exact-match CORS allowlist and serves `POST /mcp`
 * (the 8 dashboard MCP tools) through its shared route dispatch. Nothing is
 * reimplemented here, so HTTP and MCP responses stay byte-identical to the
 * standalone worker.
 *
 * Isolation: index.ts loads this module lazily through
 * `runIsolated("dashboard-api", () => import("./dashboard-api"), ...)` — a
 * dashboard-api failure degrades only `/dashboard-api/*` paths (503); every
 * other group keeps serving. This module never throws for unknown paths: it
 * forwards everything under the prefix and lets dashboard-api answer its own
 * 400 envelope.
 *
 * Secrets: reads SUPABASE_* / MARKET_DATA_URL / MCP_EDGE_KEY /
 * DASHBOARD_API_ALLOWED_ORIGINS from worker env when present; unset means the
 * stub lane (local tests, secretless dev) — never a silent synthesized
 * fallback beyond what the standalone worker already does. No secret/config
 * changes ship in this slice (the standalone worker stays deployed until
 * cutover); no new public hostnames or routes (no digiquant.io wiring here).
 */

import dashboardApi, {
  type Env as DashboardApiEnv,
} from "../../dashboard-api/src/index";
import { MCP_TOOLS } from "../../dashboard-api/src/mcp";

/** Canonical module path for the folded dashboard-api routes. */
export const DASHBOARD_API_PREFIX = "/dashboard-api";

/**
 * The 8 dashboard MCP tools, merged into the stack worker unchanged (same
 * tool defs, one shared dispatch via `POST /dashboard-api/mcp`). Re-exported
 * here so the merge is importable and pinnable without reimplementation.
 */
export { MCP_TOOLS as DASHBOARD_MCP_TOOLS };

export function isDashboardApiPath(pathname: string): boolean {
  return (
    pathname === DASHBOARD_API_PREFIX ||
    pathname.startsWith(`${DASHBOARD_API_PREFIX}/`)
  );
}

export function stripDashboardApiPrefix(pathname: string): string {
  if (pathname === DASHBOARD_API_PREFIX) {
    return "/";
  }
  return pathname.slice(DASHBOARD_API_PREFIX.length);
}

/** Worker env subset the folded dashboard-api reads (all optional). */
export interface DashboardCapableEnv {
  SUPABASE_URL?: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
  MARKET_DATA_URL?: string;
  MCP_EDGE_KEY?: string;
  DASHBOARD_API_ALLOWED_ORIGINS?: string;
}

export async function handleDashboardApi(
  request: Request,
  workerEnv: DashboardCapableEnv,
  url: URL,
): Promise<Response> {
  const target = new URL(url.toString());
  target.pathname = stripDashboardApiPrefix(url.pathname);
  const forwarded = new Request(target.toString(), request);
  return dashboardApi.fetch(forwarded, workerEnv as DashboardApiEnv);
}
