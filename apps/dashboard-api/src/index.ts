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
import { MCP_PATH, handleMcp } from "./mcp";

export const HOUSE_WORKSPACE_ID = "6b753576-ced9-5319-9bfa-c5d0aacd9319" as const;

export interface Env {
  SUPABASE_URL?: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
  /** Secret for POST /mcp (`x-digi-mcp-key`); unset = deny all (fail closed). */
  MCP_EDGE_KEY?: string;
  /** Comma-separated CORS allowlist override (issue #4679); defaults cover
   * the production dashboard plus local dashboard dev servers. */
  DASHBOARD_API_ALLOWED_ORIGINS?: string;
}

export type ErrorCode = "bad_request" | "not_found" | "upstream_empty" | "internal";

export interface Provenance {
  source: string;
  tip_date: string | null;
  contract: "finalized_accounting" | "legacy_estimate" | null;
  seam: boolean;
  marks: "stored" | "market_api" | "unavailable";
}

const ERROR_STATUS: Record<ErrorCode, number> = {
  bad_request: 400,
  not_found: 404,
  upstream_empty: 502,
  internal: 500,
};

/** Contract section 2 error envelope — the only failure shape. */
export function errorResponse(
  code: ErrorCode,
  message: string,
  retrievalPin: string | null,
  details: Record<string, unknown> = {},
): Response {
  return Response.json(
    { error: { code, message, details, retrieval_pin: retrievalPin } },
    { status: ERROR_STATUS[code] },
  );
}

/** Contract section 1 provenance object — every success carries one. */
export function buildProvenance(partial: Partial<Provenance> & Pick<Provenance, "source">): Provenance {
  return {
    tip_date: null,
    contract: null,
    seam: false,
    marks: "unavailable",
    ...partial,
  };
}

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

/** Provenance marker for the no-credential stub branch (see buildRouteTable). */
export const STUB_PROVENANCE_SOURCE = "stub-doubles-no-supabase-env";

/**
 * Rewrite a stub-served success envelope so its provenance names the stub
 * branch instead of a real table. Only success envelopes carrying a
 * `provenance` object are touched; error envelopes (§2), `/healthz`, and
 * non-JSON bodies pass through byte-for-byte.
 */
async function markStubProvenance(res: Response): Promise<Response> {
  if (res.status < 200 || res.status >= 300) return res;
  if (!(res.headers.get("content-type") ?? "").includes("application/json")) return res;
  let body: unknown;
  try {
    body = await res.clone().json();
  } catch {
    return res;
  }
  if (body === null || typeof body !== "object" || Array.isArray(body)) return res;
  const rec = body as Record<string, unknown>;
  const provenance = rec.provenance;
  if (provenance === null || typeof provenance !== "object" || Array.isArray(provenance)) return res;
  return Response.json(
    { ...rec, provenance: { ...(provenance as Record<string, unknown>), source: STUB_PROVENANCE_SOURCE } },
    { status: res.status, headers: res.headers },
  );
}

function buildRouteTable(env: Env): {
  routes: Map<string, RouteHandler>;
  ledgerBook: SupabaseSource["ledger"];
  stubbed: boolean;
} {
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
    return { routes, ledgerBook: source.ledger, stubbed: false };
  }
  // Stub branch: every mounted success is stamped so fabricated numbers can
  // never claim a committed-accounting provenance (DIG-2697).
  const addStubRoute: AddRoute = (method, path, handler) => {
    routes.set(`${method} ${path}`, failClosed(async (req: Request) => markStubProvenance(await handler(req))));
  };
  mountEnvelopeRoutes(addStubRoute, stubEnvelopeSource());
  const stubOnGet = adaptOnGet(addStubRoute);
  registerBriefRoutes(stubOnGet, stubBriefDeps());
  registerPerformanceRoutes(stubOnGet, stubPerformanceDeps());
  registerLiveRoutes(stubOnGet, stubLiveDeps());
  registerBenchmarksRoutes(stubOnGet, stubBenchmarksDeps());
  return { routes, ledgerBook: stubLedgerBook(), stubbed: true };
}

/** GET dispatch shared by HTTP and the MCP tools (same builders, one path). */
async function routeGet(request: Request, env: Env): Promise<Response> {
  const { routes, ledgerBook, stubbed } = buildRouteTable(env);
  const url = new URL(request.url);
  const path = normalizePath(url.pathname);
  if (request.method === "GET" && path === "/healthz") return handleHealthz();
  if (request.method === "GET" && path === "/ledger") {
    try {
      const res = await tryHandleLedger(request, ledgerBook);
      // /ledger resolves its own book, bypassing the mounted route table, so
      // the stub stamp is applied here (DIG-2697).
      if (res) return stubbed ? markStubProvenance(res) : res;
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
  }
  return errorResponse("bad_request", `unknown route ${path}`, null, { path });
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
