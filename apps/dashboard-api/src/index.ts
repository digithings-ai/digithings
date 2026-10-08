/**
 * dashboard-api — central read-only dashboard API (Cloudflare Worker).
 *
 * Contract: apps/dashboard-api/CONTRACT.md. All digi product names stay
 * lowercase. No auth/session changes, no digikey/ code, no
 * digiquant/brokers/ code, no live-trading paths, no new public
 * hostname/routes on any domain (human gate).
 *
 * Slice 2 scaffold: router + error envelope + provenance builder +
 * GET /healthz + GET /portfolio (with the book_as_of gate folded in per
 * CONTRACT.md section 0 — there is no standalone /book-date route).
 *
 * Slice 0006 wiring: all other contracted routes are mounted onto the
 * slice builders via `mountEnvelopeRoutes` (slice 0003),
 * `register*Routes` through `adaptOnGet` (slice 0004), and
 * `tryHandleLedger` (slice 0005), over the `./supabase` real source when the
 * worker carries `SUPABASE_SERVICE_ROLE_KEY`, else the clearly-marked stub
 * doubles in `./stubs` (slice 0008 rewire).
 * Slice 0007 decision (a): CONTRACT §6.1 documents the envelope builder's
 * `invested.definition` key, so GET /portfolio is served by the envelope
 * mount like every other route — no quarantine.
 * `POST /mcp` exposes the same routes as JSON-RPC tools (see `./mcp`).
 */

import { buildManifest, callerFor, grantedRoutes, routeVerdict, tierAtLeast } from "./access";
import { adaptOnGet } from "./adapters";
import { corsHeaders, resolveAllowlist, withCors } from "./cors";
import { mountEnvelopeRoutes, type AddRoute, type RouteHandler } from "./envelope";
import { tryHandleLedger } from "./ledger";
import { tryHandleTables } from "./tables";
import { registerBriefRoutes } from "./brief";
import { registerPerformanceRoutes } from "./performance";
import { registerLiveRoutes } from "./kpis-live";
import { registerBenchmarksRoutes } from "./benchmarks";
import {
  stubBenchmarksDeps,
  stubBriefDeps,
  stubEnvelopeSource,
  stubLedgerBook,
  stubLiveDeps,
  stubPerformanceDeps,
} from "./stubs";
import {
  UpstreamError,
  createSupabaseSource,
  hasSupabaseEnv,
  type SupabaseSource,
} from "./supabase";
import { MCP_PATH, STANDALONE_PATHS, handleMcp, secretlessStubLane } from "./mcp";
import { buildProvenance, errorResponse } from "./errors";
import { buildRegistry, userIdFor } from "./routes";
import type { Method } from "./routes/registry";


export interface Env {
  SUPABASE_URL?: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
  /** Secret for POST /mcp (`x-digi-mcp-key`); unset = deny all (fail closed). */
  MCP_EDGE_KEY?: string;
  /** Secret the edge sends as `x-digi-edge-key`; when set, identity headers without it are ignored. Set on every deployed worker. */
  DASHBOARD_EDGE_KEY?: string;
  /** Local dev / tests only: trust identity headers when DASHBOARD_EDGE_KEY is unset. */
  DASHBOARD_TRUST_IDENTITY_HEADERS?: string;
  /** Comma-separated CORS allowlist override (issue #4679); defaults cover
   * the production dashboard plus local dashboard dev servers. */
  DASHBOARD_API_ALLOWED_ORIGINS?: string;
  /** Local dev only: caller used when a request has no identity headers, e.g. "enterprise+12x". */
  DASHBOARD_DEV_CALLER?: string;
  /** Optional twelve-x (FX hub) Supabase project; absent = FX reads fail closed (upstream_empty). */
  TWELVEX_SUPABASE_URL?: string;
  TWELVEX_SUPABASE_SERVICE_KEY?: string;
}

export { buildProvenance, errorResponse, type ErrorCode, type Provenance } from "./errors";

export interface CommonParams {
  asOf: string | null;
  retrievalPin: string | null;
}

const AS_OF_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Contract section 1 common query params. Throws a Response (the error
 * envelope) on malformed input so handlers can `catch (e) return e`.
 */
export function parseCommonParams(url: URL): CommonParams {
  const retrievalPin = url.searchParams.get("retrieval_pin");
  if (retrievalPin !== null && retrievalPin.length > 128) {
    throw errorResponse("bad_request", "retrieval_pin exceeds 128 characters", null, {
      max_length: 128,
    });
  }
  const asOf = url.searchParams.get("asOf");
  if (asOf !== null) {
    const d = new Date(`${asOf}T00:00:00Z`);
    if (!AS_OF_RE.test(asOf) || Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== asOf) {
      throw errorResponse("bad_request", "asOf must be a calendar date YYYY-MM-DD", retrievalPin, {
        asOf,
      });
    }
  }
  return { asOf, retrievalPin };
}

function normalizePath(pathname: string): string {
  if (pathname.length > 1 && pathname.endsWith("/")) return pathname.slice(0, -1);
  return pathname || "/";
}

async function handleHealthz(): Promise<Response> {
  return Response.json({ ok: true, service: "dashboard-api" });
}

// --- Slice 0006 wiring (slice 0008: real sources) ------------------------------
// Route table is built per request from `env`: when the worker carries the
// Supabase service-role key the builders read real house-book rows; otherwise
// (local tests, secretless dev) the clearly-marked `./stubs` doubles serve.
// Fail-closed: an `UpstreamError` from a real read becomes the contract §2
// `upstream_empty` (502) envelope — never a silent stub fallback.

/** Wrap a route handler so upstream failures fail closed with 502. */
function failClosed(handler: RouteHandler): RouteHandler {
  return async (req: Request) => {
    try {
      return await handler(req);
    } catch (err) {
      if (err instanceof UpstreamError) {
        const pin = new URL(req.url).searchParams.get("retrieval_pin");
        return errorResponse("upstream_empty", err.message, pin, { upstream_status: err.status });
      }
      throw err;
    }
  };
}

function buildRouteTable(env: Env): { routes: Map<string, RouteHandler>; ledgerBook: SupabaseSource["ledger"] } {
  const routes = new Map<string, RouteHandler>();
  const addRoute: AddRoute = (method, path, handler) => {
    routes.set(`${method} ${path}`, failClosed(handler));
  };
  if (hasSupabaseEnv(env)) {
    const source = createSupabaseSource(env);
    mountEnvelopeRoutes(addRoute, source.envelope);
    const onGet = adaptOnGet(addRoute);
    registerBriefRoutes(onGet, source.brief);
    registerPerformanceRoutes(onGet, source.performance);
    registerLiveRoutes(onGet, source.live);
    registerBenchmarksRoutes(onGet, source.benchmarks);
    return { routes, ledgerBook: source.ledger };
  }
  mountEnvelopeRoutes(addRoute, stubEnvelopeSource());
  const onGet = adaptOnGet(addRoute);
  registerBriefRoutes(onGet, stubBriefDeps());
  registerPerformanceRoutes(onGet, stubPerformanceDeps());
  registerLiveRoutes(onGet, stubLiveDeps());
  registerBenchmarksRoutes(onGet, stubBenchmarksDeps());
  return { routes, ledgerBook: stubLedgerBook() };
}

/** GET dispatch shared by HTTP and the MCP tools (same builders, one path). */
async function routeGet(request: Request, env: Env): Promise<Response> {
  const { routes, ledgerBook } = buildRouteTable(env);
  const url = new URL(request.url);
  const path = normalizePath(url.pathname);
  if (request.method === "GET" && path === "/healthz") return handleHealthz();
  if (request.method !== "GET") return routeWrite(request, env, path);
  if (request.method === "GET" && path !== "/access/manifest") {
    // Secretless stub lane keeps the contracted doubles (200 §1). An identified
    // caller, including explicit free, is still refused when the manifest says so.
    const stubContract = secretlessStubLane(request, env) && STANDALONE_PATHS.has(path);
    if (!stubContract) {
      const manifest = buildManifest(callerFor(request, env));
      if (routeVerdict(manifest, path) === "forbidden") {
        return errorResponse("forbidden", `${path} is not available to this caller`, url.searchParams.get("retrieval_pin"), { path, tier: manifest.caller.tier });
      }
    }
  }
  if (request.method === "GET" && path === "/access/manifest") {
    const manifest = buildManifest(callerFor(request, env));
    return Response.json({
      data: { ...manifest, routes: grantedRoutes(manifest) },
      as_of: null,
      retrieval_pin: url.searchParams.get("retrieval_pin"),
      provenance: buildProvenance({ source: "access_policy" }),
    });
  }
  if (request.method === "GET" && path === "/ledger") {
    try {
      const res = await tryHandleLedger(request, ledgerBook);
      if (res) return res;
    } catch (err) {
      if (err instanceof UpstreamError) {
        return errorResponse("upstream_empty", err.message, url.searchParams.get("retrieval_pin"), {
          upstream_status: err.status,
        });
      }
      throw err;
    }
  }
  if (request.method === "GET" && path.startsWith("/v1/tables/")) {
    // Raw tables carry paid-tier data (ledger, attribution, trace): brief and above only.
    // With no Supabase and no caller, fail closed as upstream_empty (502) instead of 403.
    const caller = callerFor(request, env);
    if (!secretlessStubLane(request, env) && !tierAtLeast(caller, "brief")) {
      return errorResponse("forbidden", `${path} is not available to this caller`, url.searchParams.get("retrieval_pin"), { path, tier: caller.tier });
    }
    try {
      const res = await tryHandleTables(request, env);
      if (res) return res;
    } catch (err) {
      if (err instanceof UpstreamError) {
        return errorResponse("upstream_empty", err.message, url.searchParams.get("retrieval_pin"), {
          upstream_status: err.status,
        });
      }
      throw err;
    }
  }
  if (request.method === "GET") {
    const handler = routes.get(`GET ${path}`);
    if (handler) return handler(request);
    // Domain modules (src/routes): exact or `{param}` template paths, same gate as above.
    const hit = buildRegistry().match("GET", path);
    if (hit) {
      // Registry routes must be named in the catalog; an uncatalogued read fails closed.
      if (routeVerdict(buildManifest(callerFor(request, env)), path) !== "allowed") {
        return errorResponse("forbidden", `${path} is not available to this caller`, url.searchParams.get("retrieval_pin"), { path });
      }
      const caller = callerFor(request, env);
      return failClosed((req) => hit.fn(req, { env, params: hit.params, userId: userIdFor(req, env), caller }))(request);
    }
  }
  return errorResponse("bad_request", `unknown route ${path}`, null, { path });
}

/**
 * Writes (PUT/POST/DELETE): only registered routes exist; each needs a verified
 * user (`x-digi-user`, 401) and a catalog route the caller's manifest grants (403).
 * Ungoverned write paths fail closed. No auth/session logic lives here.
 */
async function routeWrite(request: Request, env: Env, path: string): Promise<Response> {
  const pin = new URL(request.url).searchParams.get("retrieval_pin");
  const hit = buildRegistry().match(request.method as Method, path);
  if (!hit) return errorResponse("bad_request", `unknown route ${path}`, null, { path, method: request.method });
  const userId = userIdFor(request, env);
  if (!userId) return errorResponse("unauthorized", "writes require a verified user (x-digi-user)", pin, { path });
  const manifest = buildManifest(callerFor(request, env));
  if (routeVerdict(manifest, path) !== "allowed") {
    return errorResponse("forbidden", `${request.method} ${path} is not available to this caller`, pin, { path, tier: manifest.caller.tier });
  }
  return failClosed((req) => hit.fn(req, { env, params: hit.params, userId, caller: manifest.caller }))(request);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // CORS (issue #4679): preflight short-circuit + ACAO/Vary on every
    // response, mirroring the stack market-data worker. No ACAO for
    // non-allowlisted origins (Vary: Origin still attached).
    const cors = corsHeaders(request.headers.get("Origin"), resolveAllowlist(env));
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    const url = new URL(request.url);
    const path = normalizePath(url.pathname);
    const res =
      path === MCP_PATH ? await handleMcp(request, env, (req) => routeGet(req, env)) : await routeGet(request, env);
    return withCors(res, cors);
  },
};
