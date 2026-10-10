/**
 * Slice 0006 — read-only MCP-style discovery over the dashboard-api routes.
 *
 * `POST /mcp` speaks JSON-RPC `tools/list` + `tools/call` (one tool per
 * catalog GET route: curated names for the original eight, the rest generated
 * from `DESKS`; all behind the same gate as HTTP). Secret-gated EXACTLY like the `/_stack/mcp` precedent
 * (`x-digi-mcp-key` vs env secret, fail-closed 401).
 *
 * Sharing rule: tools NEVER reimplement route logic. Each `tools/call`
 * builds a synthetic GET `Request` for the matching route and runs it
 * through the worker's own dispatch, so the MCP response is byte-identical
 * to the HTTP response from the same builder functions.
 *
 * No new public hostname or domain routes (human gate) — local
 * `wrangler dev` only. No Python/FastMCP; this is a TS worker.
 */

import { anonymousCaller, buildManifest, callerFor, governedRoutes, routeVerdict, type Manifest } from './access';
import { hasSupabaseEnv, type SupabaseEnv } from './supabase';

export const MCP_PATH = '/mcp';
export const MCP_KEY_HEADER = 'x-digi-mcp-key';

export interface McpEnv extends SupabaseEnv {
  MCP_EDGE_KEY?: string;
  DASHBOARD_DEV_CALLER?: string;
}

export interface McpToolDef {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  /** Route path this tool reads through; `{name}` segments are filled from the same-named argument. */
  path: string;
  /** Query params forwarded from tool arguments (in order). */
  params: readonly string[];
}

const STR = { type: 'string' };

/** Hand-written tools: the original names, kept stable (clients depend on them). */
const CURATED_TOOLS: readonly McpToolDef[] = [
  {
    name: 'get_access_manifest',
    description: 'Desks, pages, blocks and data routes visible to the caller, with locked reasons (contract §6.9). Call first to learn what else you may read.',
    inputSchema: { type: 'object', properties: {} },
    path: '/access/manifest',
    params: [],
  },
  {
    name: 'get_portfolio',
    description: 'Committed-book snapshot + invested envelope (contract §6.1).',
    inputSchema: {
      type: 'object',
      properties: { asOf: STR, retrieval_pin: STR },
    },
    path: '/portfolio',
    params: ['asOf', 'retrieval_pin'],
  },
  {
    name: 'get_allocations',
    description: 'Reconciled allocation rows with folded valuations (contract §6.2).',
    inputSchema: {
      type: 'object',
      properties: { asOf: STR, retrieval_pin: STR, include_marks: STR },
    },
    path: '/allocations',
    params: ['asOf', 'retrieval_pin', 'include_marks'],
  },
  {
    name: 'get_nav_series',
    description: 'Shared NAV + close series (contract §6.6).',
    inputSchema: {
      type: 'object',
      properties: { asOf: STR, retrieval_pin: STR, from: STR, to: STR },
    },
    path: '/nav-series',
    params: ['asOf', 'retrieval_pin', 'from', 'to'],
  },
  {
    name: 'get_brief',
    description: 'Brief scoreboard KPIs with persisted-vs-overlay decision (contract §6.3).',
    inputSchema: {
      type: 'object',
      properties: { asOf: STR, retrieval_pin: STR, overlay: STR },
    },
    path: '/brief',
    params: ['asOf', 'retrieval_pin', 'overlay'],
  },
  {
    name: 'get_performance',
    description: 'Tearsheet bundle: NAV series + benchmark-relative headline (contract §6.4).',
    inputSchema: {
      type: 'object',
      properties: { asOf: STR, retrieval_pin: STR, benchmark: STR, window: STR },
    },
    path: '/performance',
    params: ['asOf', 'retrieval_pin', 'benchmark', 'window'],
  },
  {
    name: 'get_kpis_live',
    description: 'Point-in-time live snapshot, never a stream (contract §6.5).',
    inputSchema: { type: 'object', properties: { retrieval_pin: STR } },
    path: '/kpis/live',
    params: ['retrieval_pin'],
  },
  {
    name: 'get_benchmarks',
    description: 'Benchmark universe + aligned series for a NAV window (contract §6.7).',
    inputSchema: {
      type: 'object',
      properties: { retrieval_pin: STR, tickers: STR, from: STR, to: STR },
    },
    path: '/benchmarks',
    params: ['retrieval_pin', 'tickers', 'from', 'to'],
  },
  {
    name: 'get_ledger',
    description: 'Ledger event stream from the house book (contract §6.8).',
    inputSchema: {
      type: 'object',
      properties: { asOf: STR, retrieval_pin: STR, ticker: STR, limit: STR, cursor: STR },
    },
    path: '/ledger',
    params: ['asOf', 'retrieval_pin', 'ticker', 'limit', 'cursor'],
  },
];

const PATH_PARAM = /\{(\w+)\}/g;

/** `/fx/pairs/{pair}/path` -> `get_fx_pairs_pair_path`. */
export function toolNameFor(route: string): string {
  return 'get_' + route.replace(PATH_PARAM, '$1').split('/').filter(Boolean).join('_').replace(/[^A-Za-z0-9_]/g, '_');
}

/** One generated tool per catalog GET route that no curated tool already covers. */
function generatedTools(covered: ReadonlySet<string>): McpToolDef[] {
  return governedRoutes()
    .filter((r) => !covered.has(r))
    .sort()
    .map((route) => {
      const pathParams = [...route.matchAll(PATH_PARAM)].map((m) => m[1]!);
      const props: Record<string, unknown> = Object.fromEntries(pathParams.map((p) => [p, STR]));
      Object.assign(props, { asOf: STR, retrieval_pin: STR });
      return {
        name: toolNameFor(route),
        description: `Read ${route} (same route, same access gate as the app; see get_access_manifest).`,
        inputSchema: { type: 'object', properties: props, ...(pathParams.length ? { required: pathParams } : {}) },
        path: route,
        params: ['asOf', 'retrieval_pin'],
      };
    });
}

/** Curated tools first, then one tool per remaining catalog route (generated from `DESKS`). */
export const MCP_TOOLS: readonly McpToolDef[] = [
  ...CURATED_TOOLS,
  ...generatedTools(new Set(CURATED_TOOLS.map((t) => t.path))),
];

/**
 * The original eight dashboard tools. The folded stack worker exposes this
 * list — not `MCP_TOOLS`, and not the digiquant server manifest.
 */
export const STANDALONE_MCP_TOOLS: readonly McpToolDef[] = CURATED_TOOLS.filter(
  (t) => t.path !== '/access/manifest',
);

export const STANDALONE_PATHS: ReadonlySet<string> = new Set(STANDALONE_MCP_TOOLS.map((t) => t.path));

/**
 * No Supabase and no caller identity. Contracted routes keep their stub
 * envelopes; an identified caller (including explicit `free`) stays gated.
 */
export function secretlessStubLane(request: Request, env: McpEnv): boolean {
  return anonymousCaller(request, env) && !hasSupabaseEnv(env);
}

/** Concrete route path for a call, or an error message when a path argument is missing. */
function resolvePath(tool: McpToolDef, args: Record<string, unknown>): { path: string } | { error: string } {
  let missing: string | null = null;
  const path = tool.path.replace(PATH_PARAM, (_m, name: string) => {
    const v = args[name];
    if (typeof v !== 'string' || v.trim() === '' || v === '.' || v === '..') missing = name; // '..' would let the URL parser climb out of the gated route
    return encodeURIComponent(String(v ?? ''));
  });
  return missing ? { error: `missing required argument ${missing}` } : { path };
}

/**
 * Secret gate mirroring the `/_stack/mcp` precedent: the `x-digi-mcp-key`
 * header must match the env secret. Fail closed — no secret configured,
 * missing header, or mismatch all deny.
 */
export function mcpAuthorized(request: Request, env: McpEnv): boolean {
  const expected = (env.MCP_EDGE_KEY ?? '').trim();
  const provided = (request.headers.get(MCP_KEY_HEADER) ?? '').trim();
  if (!expected || !provided || provided !== expected) return false;
  return true;
}

type JsonRpcId = string | number | null;
interface JsonRpcRequest {
  jsonrpc?: unknown;
  id?: JsonRpcId;
  method?: unknown;
  params?: unknown;
}

function rpcError(id: JsonRpcId, code: number, message: string): Response {
  return Response.json({ jsonrpc: '2.0', id, error: { code, message } });
}

function toolResultText(tool: McpToolDef, args: Record<string, unknown>): URLSearchParams {
  const query = new URLSearchParams();
  for (const key of tool.params) {
    const value = args[key];
    if (value !== undefined && value !== null) query.set(key, String(value));
  }
  return query;
}

/** MCP gate = the app's gate: a tool is visible and callable only if the caller's manifest grants its route. */
function toolAllowed(tool: McpToolDef, m: Manifest): boolean {
  return routeVerdict(m, tool.path) !== 'forbidden';
}

async function handleOne(
  raw: unknown,
  dispatch: (req: Request) => Promise<Response>,
  m: Manifest,
  identity: Record<string, string>,
  stub: boolean,
): Promise<Record<string, unknown>> {
  const req = (raw ?? {}) as JsonRpcRequest;
  const id: JsonRpcId = req.id ?? null;
  if (req.jsonrpc !== '2.0' || typeof req.method !== 'string') {
    return { jsonrpc: '2.0', id, error: { code: -32600, message: 'invalid request' } };
  }
  if (req.method === 'tools/list') {
    return {
      jsonrpc: '2.0',
      id,
      result: {
        tools: (stub ? STANDALONE_MCP_TOOLS : MCP_TOOLS.filter((t) => toolAllowed(t, m))).map((t) => ({
          name: t.name,
          description: t.description,
          inputSchema: t.inputSchema,
        })),
      },
    };
  }
  if (req.method === 'tools/call') {
    const params = (req.params ?? {}) as { name?: unknown; arguments?: unknown };
    const tool = MCP_TOOLS.find((t) => t.name === params.name);
    if (!tool) {
      return { jsonrpc: '2.0', id, error: { code: -32602, message: `unknown tool ${String(params.name)}` } };
    }
    const args =
      params.arguments !== undefined && params.arguments !== null
        ? (params.arguments as Record<string, unknown>)
        : {};
    if (typeof args !== 'object' || Array.isArray(args)) {
      return { jsonrpc: '2.0', id, error: { code: -32602, message: 'arguments must be an object' } };
    }
    const standalone = STANDALONE_MCP_TOOLS.some((t) => t.name === tool.name);
    if (!(stub && standalone) && !toolAllowed(tool, m)) {
      return { jsonrpc: '2.0', id, error: { code: -32003, message: `forbidden: ${tool.name} is not available to this caller (tier ${m.caller.tier})` } };
    }
    // Shared service layer: run the worker's own route handler (identity forwarded, so the HTTP gate agrees).
    const resolved = resolvePath(tool, args);
    if ('error' in resolved) return { jsonrpc: '2.0', id, error: { code: -32602, message: resolved.error } };
    const url = `https://internal${resolved.path}?${toolResultText(tool, args).toString()}`;
    const res = await dispatch(new Request(url, { method: 'GET', headers: identity }));
    const text = await res.text();
    return {
      jsonrpc: '2.0',
      id,
      result: { content: [{ type: 'text', text }], isError: res.status >= 400 },
    };
  }
  return { jsonrpc: '2.0', id, error: { code: -32601, message: `method not found: ${req.method}` } };
}

/**
 * Handle `POST /mcp`. `dispatch` is the worker's own route dispatch
 * (same handlers as HTTP) — tools share it verbatim.
 */
export async function handleMcp(
  request: Request,
  env: McpEnv,
  dispatch: (req: Request) => Promise<Response>,
): Promise<Response> {
  if (request.method !== 'POST') {
    return Response.json(
      { error: { code: 'bad_request', message: 'POST only', details: {}, retrieval_pin: null } },
      { status: 400 },
    );
  }
  if (!mcpAuthorized(request, env)) {
    // Stack precedent: plain fail-closed 401, no envelope.
    return new Response('dashboard-api: unauthorized', { status: 401 });
  }
  const m = buildManifest(callerFor(request, env));
  const stub = secretlessStubLane(request, env);
  const identity: Record<string, string> = {};
  for (const h of ['x-digi-tier', 'x-digi-groups', 'x-digi-edge-key']) {
    const v = request.headers.get(h);
    if (v !== null) identity[h] = v;
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return rpcError(null, -32700, 'parse error');
  }
  if (Array.isArray(body)) {
    if (body.length === 0) return rpcError(null, -32600, 'invalid request');
    const out = [];
    for (const item of body) out.push(await handleOne(item, dispatch, m, identity, stub));
    return Response.json(out);
  }
  return Response.json(await handleOne(body, dispatch, m, identity, stub));
}
