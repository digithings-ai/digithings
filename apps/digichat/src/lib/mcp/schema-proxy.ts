/**
 * Schema-normalizing MCP passthrough (DC-18).
 *
 * An agent runtime that fetches an MCP server's tool list itself (Azure AI
 * Foundry's `mcp` tool does) never lets digichat see the schemas. Pointing the
 * agent's MCP `server_url` at `/api/mcp-proxy/<label>` puts digichat in the
 * path, and this module then:
 *
 * - forwards every request to the ONE upstream configured for `<label>`
 *   (`DIGICHAT_MCP_SCHEMA_PROXY`, a server-only JSON map) — never to a URL the
 *   caller names, so this is not an open proxy;
 * - rewrites each `tools/list` result through {@link normalizeToolsListResult}
 *   and remembers the ORIGINAL schemas per tool;
 * - reshapes each `tools/call`'s arguments back onto the original schema
 *   ({@link coerceToolArguments}) before forwarding.
 *
 * - optionally (`toolErrorsAsResults`, per label) restates a tool's `isError`
 *   result as an ordinary result that names the error, so the model can
 *   correct the call or explain the failure instead of the runtime ending the
 *   turn.
 *
 * It adds no credentials. The caller's own auth headers (e.g. the agent
 * connection's `X-API-Key`) are forwarded as-is and nothing is logged about
 * them. Both JSON and `text/event-stream` (Streamable HTTP) replies are handled.
 */
import { coerceToolArguments, normalizeToolsListResult } from "@/lib/mcp/schema-normalize";

export const SCHEMA_PROXY_ENV = "DIGICHAT_MCP_SCHEMA_PROXY";
const LABEL_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;
const MAX_BODY_BYTES = 1_000_000;
const PROBE_ID = "digichat-schema-proxy-probe";

const STRIPPED_REQUEST_HEADERS = new Set([
  "host",
  "content-length",
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "accept-encoding",
  "cookie",
  "forwarded",
  "x-forwarded-for",
  "x-forwarded-host",
  "x-forwarded-proto",
]);
const STRIPPED_RESPONSE_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "content-encoding",
  "content-length",
  "set-cookie",
]);

type JsonRpcMessage = {
  jsonrpc?: string;
  id?: string | number | null;
  method?: string;
  params?: Record<string, unknown>;
  result?: unknown;
};

/** label → original inputSchema per tool name. Module-level: survives requests, not restarts. */
const originalSchemas = new Map<string, Map<string, unknown>>();

export function resetSchemaProxyCacheForTests(): void {
  originalSchemas.clear();
}

export interface SchemaProxyTarget {
  url: string;
  /**
   * Hand a tool's `isError` result back to the model as an ordinary result
   * that says what went wrong, instead of letting the agent runtime end the
   * turn on it (Foundry fails the whole response on an `isError` MCP result).
   * Opt-in per label: `{"<label>": {"url": "...", "toolErrorsAsResults": true}}`.
   */
  toolErrorsAsResults: boolean;
}

/**
 * The configured target for `label`, or null. The env value maps a label to an
 * upstream URL string, or to `{ url, toolErrorsAsResults? }`. Only https, or
 * http to a loopback host; no userinfo.
 */
export function schemaProxyTarget(
  label: string,
  env: Record<string, string | undefined> = process.env,
): SchemaProxyTarget | null {
  if (!LABEL_RE.test(label)) return null;
  const raw = env[SCHEMA_PROXY_ENV]?.trim();
  if (!raw) return null;
  let map: unknown;
  try {
    map = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isObject(map)) return null;
  const entry = map[label];
  const value = typeof entry === "string" ? entry : isObject(entry) ? entry.url : undefined;
  if (typeof value !== "string") return null;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  const loopback = url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "[::1]";
  if (url.protocol !== "https:" && !(url.protocol === "http:" && loopback)) return null;
  if (url.username || url.password) return null;
  return { url: url.href, toolErrorsAsResults: isObject(entry) && entry.toolErrorsAsResults === true };
}

/** The configured upstream URL for `label`, or null. */
export function schemaProxyUpstream(label: string, env: Record<string, string | undefined> = process.env): string | null {
  return schemaProxyTarget(label, env)?.url ?? null;
}

function pickHeaders(from: Headers, drop: Set<string>): Headers {
  const out = new Headers();
  from.forEach((value, name) => {
    if (!drop.has(name.toLowerCase())) out.set(name, value);
  });
  return out;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function cacheFor(label: string): Map<string, unknown> {
  let m = originalSchemas.get(label);
  if (!m) {
    m = new Map();
    originalSchemas.set(label, m);
  }
  return m;
}

function remember(label: string, result: unknown): void {
  if (!isObject(result) || !Array.isArray(result.tools)) return;
  const cache = cacheFor(label);
  for (const tool of result.tools) {
    if (isObject(tool) && typeof tool.name === "string" && tool.inputSchema !== undefined) {
      cache.set(tool.name, tool.inputSchema);
    }
  }
}

/** Parse every JSON-RPC message out of an SSE body (`data:` lines, blank-line framed). */
function messagesFromSse(text: string): unknown[] {
  const out: unknown[] = [];
  for (const block of text.split(/\r?\n\r?\n/)) {
    const data = block
      .split(/\r?\n/)
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).replace(/^ /, ""))
      .join("\n");
    if (!data) continue;
    try {
      out.push(JSON.parse(data));
    } catch {
      /* not JSON: ignore */
    }
  }
  return out;
}

/** Fetch `tools/list` once on a cache miss, with the caller's own headers. Best effort. */
async function probeToolsList(
  label: string,
  upstream: string,
  headers: Headers,
  fetchImpl: typeof fetch,
): Promise<void> {
  try {
    const res = await fetchImpl(upstream, {
      method: "POST",
      headers,
      body: JSON.stringify({ jsonrpc: "2.0", id: PROBE_ID, method: "tools/list", params: {} }),
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) return;
    const text = await res.text();
    const messages = (res.headers.get("content-type") ?? "").includes("text/event-stream")
      ? messagesFromSse(text)
      : [JSON.parse(text) as unknown].flat();
    for (const m of messages) {
      if (isObject(m) && m.id === PROBE_ID) remember(label, m.result);
    }
  } catch {
    /* forward uncoerced */
  }
}

type Rewrite = { label: string; listIds: Set<string>; softenCallIds: Set<string> };

/** A tool's `isError` result, restated as a normal result the model can act on. */
export function toolErrorAsResult(result: unknown): unknown {
  if (!isObject(result) || result.isError !== true) return result;
  const detail = (Array.isArray(result.content) ? result.content : [])
    .map((c) => (isObject(c) && c.type === "text" && typeof c.text === "string" ? c.text : ""))
    .filter(Boolean)
    .join(" ")
    .trim()
    .slice(0, 1000);
  return {
    ...result,
    isError: false,
    content: [
      {
        type: "text",
        text:
          `TOOL ERROR: ${detail || "the tool failed without saying why."} ` +
          "This call did not succeed and returned no data. If an argument looks wrong, " +
          "retry once with corrected arguments (or without the optional ones); otherwise " +
          "tell the user this lookup failed and why. Do not invent a result.",
      },
    ],
  };
}

function rewriteMessage(message: unknown, rw: Rewrite): unknown {
  if (!isObject(message) || !("result" in message)) return message;
  const id = message.id;
  if (id === undefined || id === null) return message;
  const key = JSON.stringify(id);
  if (rw.listIds.has(key)) {
    remember(rw.label, message.result);
    return { ...message, result: normalizeToolsListResult(message.result) };
  }
  if (rw.softenCallIds.has(key)) return { ...message, result: toolErrorAsResult(message.result) };
  return message;
}

function rewriteJsonBody(text: string, rw: Rewrite): string {
  try {
    const parsed = JSON.parse(text) as unknown;
    const rewritten = Array.isArray(parsed) ? parsed.map((m) => rewriteMessage(m, rw)) : rewriteMessage(parsed, rw);
    return JSON.stringify(rewritten);
  } catch {
    return text;
  }
}

/** Rewrite one SSE event block; non-data fields and non-JSON data pass through. */
function rewriteSseEvent(block: string, rw: Rewrite): string {
  const lines = block.split(/\r?\n/);
  const dataLines = lines.filter((l) => l.startsWith("data:"));
  if (dataLines.length === 0) return block;
  const data = dataLines.map((l) => l.slice(5).replace(/^ /, "")).join("\n");
  const rewritten = rewriteJsonBody(data, rw);
  if (rewritten === data) return block;
  const others = lines.filter((l) => !l.startsWith("data:"));
  return [...others, `data: ${rewritten}`].join("\n");
}

function sseRewriter(rw: Rewrite): TransformStream<Uint8Array, Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let buffer = "";
  return new TransformStream({
    transform(chunk, controller) {
      buffer += decoder.decode(chunk, { stream: true });
      let match: RegExpExecArray | null;
      const boundary = /\r?\n\r?\n/;
      while ((match = boundary.exec(buffer))) {
        const block = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        controller.enqueue(encoder.encode(`${rewriteSseEvent(block, rw)}\n\n`));
      }
    },
    flush(controller) {
      buffer += decoder.decode();
      if (buffer) controller.enqueue(encoder.encode(rewriteSseEvent(buffer, rw)));
    },
  });
}

export async function proxySchemaNormalizedMcp(
  req: Request,
  label: string,
  opts: { fetchImpl?: typeof fetch; env?: Record<string, string | undefined> } = {},
): Promise<Response> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const target = schemaProxyTarget(label, opts.env);
  if (!target) return json(404, { error: "not_found" });
  const upstream = target.url;

  const method = req.method.toUpperCase();
  const headers = pickHeaders(req.headers, STRIPPED_REQUEST_HEADERS);
  let body: string | undefined;
  const listIds = new Set<string>();
  const softenCallIds = new Set<string>();

  if (method !== "GET" && method !== "HEAD") {
    const raw = await req.arrayBuffer();
    if (raw.byteLength > MAX_BODY_BYTES) return json(413, { error: "payload_too_large" });
    body = new TextDecoder().decode(raw);
    if (method === "POST") {
      let parsed: unknown;
      try {
        parsed = JSON.parse(body);
      } catch {
        parsed = undefined;
      }
      if (parsed !== undefined) {
        const messages = (Array.isArray(parsed) ? parsed : [parsed]) as JsonRpcMessage[];
        for (const m of messages) {
          if (!isObject(m)) continue;
          if (m.method === "tools/list" && m.id !== undefined && m.id !== null) listIds.add(JSON.stringify(m.id));
          if (m.method === "tools/call" && target.toolErrorsAsResults && m.id !== undefined && m.id !== null) {
            softenCallIds.add(JSON.stringify(m.id));
          }
          if (m.method === "tools/call" && isObject(m.params) && typeof m.params.name === "string") {
            if (!cacheFor(label).has(m.params.name)) await probeToolsList(label, upstream, headers, fetchImpl);
            const original = cacheFor(label).get(m.params.name);
            if (original !== undefined && isObject(m.params.arguments)) {
              m.params = { ...m.params, arguments: coerceToolArguments(original, m.params.arguments) };
            }
          }
        }
        body = JSON.stringify(Array.isArray(parsed) ? messages : messages[0]);
      }
    }
  }

  let res: Response;
  try {
    res = await fetchImpl(upstream, { method, headers, body, redirect: "manual", cache: "no-store" });
  } catch {
    return json(502, { error: "mcp_upstream_unreachable" });
  }

  const outHeaders = pickHeaders(res.headers, STRIPPED_RESPONSE_HEADERS);
  outHeaders.set("cache-control", "no-store");
  if (method === "HEAD" || res.status === 204 || res.status === 205 || res.status === 304 || !res.body) {
    return new Response(null, { status: res.status, headers: outHeaders });
  }
  if (listIds.size === 0 && softenCallIds.size === 0) {
    return new Response(res.body, { status: res.status, headers: outHeaders });
  }
  const rw: Rewrite = { label, listIds, softenCallIds };
  const type = res.headers.get("content-type") ?? "";
  if (type.includes("text/event-stream")) {
    return new Response(res.body.pipeThrough(sseRewriter(rw)), { status: res.status, headers: outHeaders });
  }
  if (type.includes("json")) {
    const text = await res.text();
    return new Response(rewriteJsonBody(text, rw), { status: res.status, headers: outHeaders });
  }
  return new Response(res.body, { status: res.status, headers: outHeaders });
}
