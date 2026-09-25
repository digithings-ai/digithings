/**
 * Slice 0006 — read-only MCP-style discovery over the dashboard-api routes.
 *
 * `POST /mcp` speaks JSON-RPC `tools/list` + `tools/call` (one tool per
 * read-only route). Secret-gated EXACTLY like the `/_stack/mcp` precedent
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

export const MCP_PATH = '/mcp';
export const MCP_KEY_HEADER = 'x-digi-mcp-key';

export interface McpEnv {
  MCP_EDGE_KEY?: string;
}

export interface McpToolDef {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  /** Route path this tool reads through. */
  path: string;
  /** Query params forwarded from tool arguments (in order). */
  params: readonly string[];
}

const STR = { type: 'string' };

export const MCP_TOOLS: readonly McpToolDef[] = [
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

async function handleOne(
  raw: unknown,
  dispatch: (req: Request) => Promise<Response>,
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
        tools: MCP_TOOLS.map((t) => ({
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
    // Shared service layer: run the worker's own route handler.
    const url = `https://internal${tool.path}?${toolResultText(tool, args).toString()}`;
    const res = await dispatch(new Request(url, { method: 'GET' }));
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
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return rpcError(null, -32700, 'parse error');
  }
  if (Array.isArray(body)) {
    if (body.length === 0) return rpcError(null, -32600, 'invalid request');
    const out = [];
    for (const item of body) out.push(await handleOne(item, dispatch));
    return Response.json(out);
  }
  return Response.json(await handleOne(body, dispatch));
}
