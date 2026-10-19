/**
 * /api/mcp/zammad* — the OCC helpdesk (Zammad) read-only MCP passthrough.
 *
 * The zammad-mcp python server runs INSIDE this image on 127.0.0.1:8770
 * (`scripts/trusted-proxy-server.mjs` -> `startZammadMcp()`, which only starts
 * it when ZAMMAD_API_TOKEN is set). The digichat Worker gates
 * `https://digithings.ai/api/mcp/zammad*` on the `x-digi-mcp-key` header and
 * then forwards the request to the container's port 3000.
 *
 * In production DIGICHAT_TRUSTED_PROXIES is unset, so the trusted proxy does not
 * run and Next itself owns port 3000 — without this route the path falls
 * through to Next and answers with its own 404 page. This route is therefore
 * what serves it; the proxy's own `/api/mcp/zammad*` rewrite stays as a
 * harmless fallback.
 *
 * The upstream URL is the MCP endpoint itself: every `/api/mcp/zammad*` variant
 * maps to it, exactly as the trusted proxy's rewrite does. That is also why the
 * matched `[[...path]]` segments are not consumed here.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DEFAULT_UPSTREAM_URL = "http://127.0.0.1:8770/mcp";

/**
 * Request headers that must not be replayed on the next hop.
 *
 * `host` and `content-length` describe THIS hop; `fetch` computes both for the
 * request it sends, and a forwarded `content-length` is the caller's count, not
 * the bytes we re-send. The rest are hop-by-hop by definition — the same list
 * `withoutHopByHopHeaders` strips in scripts/trusted-proxy-server.mjs — and
 * three of them are rejected outright by Node's fetch (measured on node
 * v26.10.0: "invalid transfer-encoding header", "invalid keep-alive header",
 * "invalid upgrade header"), so forwarding them would turn every chunked
 * request into a 502.
 */
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
]);

/**
 * Response headers that must not be replayed either.
 *
 * `content-encoding` / `content-length` are the non-obvious pair: Node's fetch
 * decodes `content-encoding` transparently but leaves BOTH headers untouched
 * (measured on node v26.10.0 — a 45-byte gzip body arrives as 420 decoded
 * bytes while the response still claims `content-encoding: gzip` and
 * `content-length: 45`). Passing them on would tell the client to gunzip plain
 * JSON and then read 45 bytes of it.
 */
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
]);

/** Upstream MCP endpoint; overridable so the route is testable off-container. */
function upstreamUrl(): string {
  return process.env.ZAMMAD_MCP_URL?.trim() || DEFAULT_UPSTREAM_URL;
}

function pickHeaders(from: Headers, drop: Set<string>): Headers {
  const out = new Headers();
  from.forEach((value, name) => {
    if (!drop.has(name.toLowerCase())) out.set(name, value);
  });
  return out;
}

/** Never a 200: an unreachable upstream is a gateway failure, not an answer. */
function unreachableResponse(): Response {
  return new Response(JSON.stringify({ error: "zammad_mcp_unreachable" }), {
    status: 502,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

async function forward(req: Request): Promise<Response> {
  const method = req.method.toUpperCase();
  // GET/HEAD carry no body; every other method is forwarded verbatim.
  const body = method === "GET" || method === "HEAD" ? undefined : await req.arrayBuffer();

  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl(), {
      method,
      headers: pickHeaders(req.headers, STRIPPED_REQUEST_HEADERS),
      body,
      // The trusted proxy does not follow redirects either: a 3xx from the MCP
      // server is the answer, not a hop to chase.
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    // Connect/DNS/abort failure, or a header Node's fetch refuses.
    return unreachableResponse();
  }

  const headers = pickHeaders(upstream.headers, STRIPPED_RESPONSE_HEADERS);
  headers.set("cache-control", "no-store");

  // A body is forbidden on these statuses, and fetch yields none for HEAD.
  const statusForbidsBody =
    method === "HEAD" || upstream.status === 204 || upstream.status === 205 || upstream.status === 304;
  return new Response(statusForbidsBody ? null : upstream.body, {
    status: upstream.status,
    headers,
  });
}

export function GET(req: Request): Promise<Response> {
  return forward(req);
}

export function POST(req: Request): Promise<Response> {
  return forward(req);
}

export function DELETE(req: Request): Promise<Response> {
  return forward(req);
}

export function HEAD(req: Request): Promise<Response> {
  return forward(req);
}
