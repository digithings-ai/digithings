/**
 * /api/mcp-proxy/<label> — schema-normalizing MCP passthrough (DC-18).
 *
 * Off unless `DIGICHAT_MCP_SCHEMA_PROXY` maps `<label>` to an upstream MCP URL
 * (server-only env, e.g. `{"tools":"https://mcp.example.com/"}`); an unknown or
 * unconfigured label answers 404. See `src/lib/mcp/schema-proxy.ts`.
 *
 * Caller authentication. A configured proxy is an open relay to a URL only the
 * server chooses: without a gate, anyone who learns the path can drive the
 * upstream with digichat's address and digichat's egress. So a configured proxy
 * also requires a shared secret in `x-digi-mcp-key`, compared against
 * `DIGICHAT_MCP_PROXY_KEY`. The header is stripped on the way in (it is in
 * `STRIPPED_REQUEST_HEADERS`), so the secret never reaches the upstream, and
 * every other header the caller sent — their own upstream credential included —
 * is still forwarded.
 *
 * There is deliberately no "no key configured means open" branch: a proxy that
 * is configured without a key answers 503 rather than serving traffic, because
 * the failure mode of guessing wrong here is a public relay.
 */
import {
  proxySchemaNormalizedMcp,
  SCHEMA_PROXY_ENV,
} from "@/lib/mcp/schema-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PROXY_KEY_ENV = "DIGICHAT_MCP_PROXY_KEY";
const PROXY_KEY_HEADER = "x-digi-mcp-key";

type Ctx = { params: Promise<{ label: string }> };

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/**
 * Compare two secrets without leaking their length or position through timing.
 * Lengths are compared first because a differing length is already public.
 */
function secretMatches(presented: string, expected: string): boolean {
  const a = new TextEncoder().encode(presented);
  const b = new TextEncoder().encode(expected);
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a[i] ^ b[i];
  return diff === 0;
}

async function handle(req: Request, ctx: Ctx): Promise<Response> {
  // The feature flag comes before the route: with no configuration at all the
  // path does not exist, and that answer carries no information about which
  // labels are configured.
  if (!process.env[SCHEMA_PROXY_ENV]) return json(404, { error: "not_found" });

  const expected = process.env[PROXY_KEY_ENV];
  if (!expected) return json(503, { error: "proxy_key_unconfigured" });

  const presented = req.headers.get(PROXY_KEY_HEADER);
  if (!presented || !secretMatches(presented, expected)) {
    return json(401, { error: "unauthorized" });
  }

  const { label } = await ctx.params;
  return proxySchemaNormalizedMcp(req, label);
}

export const GET = handle;
export const POST = handle;
export const DELETE = handle;
