/**
 * Identity at the MCP edge (`/_stack/mcp/<id>/…`).
 *
 * The edge used to accept exactly one credential: a shared static string in
 * `x-digi-mcp-key` (see `mcpEdgeKeyFor` in index.ts). One string, no identity,
 * no scope, no per-caller revocation. This module adds the second credential
 * the deployment actually wants — a digikey JWT minted server-side for the
 * digichat BFF — and keeps the static key working unchanged for
 * compose/self-host, where there is no digikey to mint one.
 *
 * Two accepted credentials, in this order:
 *
 * 1. `x-digi-mcp-key` equal to this server's edge key (`MCP_EDGE_KEYS[id]`,
 *    else `MCP_EDGE_KEY`). Unchanged behaviour; the compat path.
 * 2. `Authorization: Bearer <digikey JWT>`, verified against the digikey JWKS
 *    and required to carry `mcp:<serverId>`.
 *
 * Precedence is "static key first": when both arrive, a matching key decides
 * and the JWT is not even parsed. A request that reaches the JWT path and
 * fails is refused — there is no third branch and no way to reach the
 * container without one of the two succeeding.
 *
 * Fail closed, always. Verification that cannot run (no JWKS URL, JWKS
 * unreachable, unknown kid after one refetch, unparseable key) refuses the
 * request; it never degrades to "allow". The failure modes are separated only
 * by status code: no/invalid credential is 401, a *valid* token that lacks the
 * server's scope is 403, and a valid token whose JSON-RPC frame the edge cannot
 * inspect is 400. That distinction is what lets a caller tell "get a token"
 * from "you were not granted this server".
 *
 * `mcp:<serverId>` is read-only. A mutating tool (see `MCP_EDGE_WRITE_SCOPES`)
 * needs its own scope, checked against the tool name in the JSON-RPC body of a
 * JWT-authenticated POST. The static-key path is unchanged: it is the
 * compose/self-host compat credential, and its write surface stays gated by the
 * server's own env flag (`DIGIVAULT_MCP_WRITE`).
 *
 * Identity, not just scope (#6648). A JWT must carry a tenant claim
 * (`tenant_slug`): a claimless token has no tenant for the server behind the
 * edge to bind its data to, so it is refused (401 `missing_tenant`). A bare
 * `*` grant is refused too (403 `wildcard_scope`) unless the token belongs to
 * the house tenant: `*` is what a CLI-default API key used to carry, and it
 * must not open another tenant's MCP server by accident. The servers behind the
 * edge still re-read the tenant from the token and bind their data to it
 * (digisearch `tenant_index_scope`, digivault `mcp_tenant`); the edge check is
 * the first of the two layers, not the only one.
 *
 * Never log the token, a prefix of it, or the key. The decision log carries the
 * server id, which credential path won, the scope and a fixed reason string.
 */

import { HOUSE_TENANT_SLUG, LIVE_HOUSE_TENANT_SLUG } from "./tenant-config";

/**
 * Scope each edge server requires to be reached at all. One entry per
 * `MCP_EDGE_SERVERS` id. This is the *read* scope: it opens the server, and
 * every tool not listed in `MCP_EDGE_WRITE_SCOPES` is reachable with it.
 */
export const MCP_EDGE_SCOPES: Record<string, string> = {
  digisearch: "mcp:digisearch",
  digivault: "mcp:digivault",
  // The digiquant MCP surface reuses the scope its HTTP API already mints
  // (`digiquant_path_scopes()` in digikey); no new scope is introduced.
  digiquant: "digiquant:backtest",
};

/**
 * Tools that mutate, and the extra scope each one needs. `mcp:<serverId>` is
 * therefore read-only: a token minted for it may search and lint, never write
 * (DIG-5723). The tool names are the wire names the MCP server advertises
 * (`@mcp.tool(name=…)` in `digivault/tool_dispatch.py`), not the
 * `digivault_`-prefixed orchestrator ids.
 *
 * The write scope is deliberately absent from digikey's
 * `BFF_SESSION_GRANTABLE_SCOPES`: a BFF session cannot ask for it, so the chat
 * can never mint a write-capable edge token. Only an admin-issued API key that
 * already carries `mcp:digivault:write` can.
 */
export const MCP_EDGE_WRITE_SCOPES: Record<string, Record<string, string>> = {
  digivault: { create_note: "mcp:digivault:write" },
};

/**
 * Tenants whose tokens may use a bare `*` grant at the edge. Both house slugs:
 * the corpus map keys the house as `digithings` and the live chat resolves it
 * as `digithings-ai` (see `tenant-config.ts`).
 */
export const MCP_EDGE_WILDCARD_TENANTS: ReadonlySet<string> = new Set([
  HOUSE_TENANT_SLUG,
  LIVE_HOUSE_TENANT_SLUG,
]);

/** The scope a caller must hold to reach `serverId`, or "" when unmapped. */
export function mcpScopeForServer(serverId: string): string {
  return MCP_EDGE_SCOPES[serverId] ?? "";
}

/**
 * The write scope `tool` needs on `serverId`, or "" when the tool is read-only
 * (or unnamed). Unknown tools need nothing extra: the server rejects a name it
 * does not advertise, and the read scope still had to pass.
 */
export function mcpWriteScopeForTool(serverId: string, tool: string): string {
  const tools = MCP_EDGE_WRITE_SCOPES[serverId];
  if (!tools) return "";
  return tools[tool] ?? "";
}

/**
 * How long a fetched JWKS is trusted. Five minutes matches digikey's own
 * `DIGIKEY_JWKS_CACHE_SEC` default (`digikey/jwt_verify.py`) and is well under
 * a rotation window, so a rotated key is picked up on its own.
 */
export const MCP_EDGE_JWKS_TTL_MS = 5 * 60_000;

/**
 * Tolerated clock difference on `exp` / `nbf` / `iat`, seconds. Same order as
 * the Python verifier's leeway; small enough that an expired token is not
 * usable for long, large enough that a Worker clock a few seconds ahead of
 * digikey does not refuse a fresh token.
 */
export const MCP_EDGE_CLOCK_SKEW_SEC = 60;

/** The worker env slice this module reads. Structurally satisfied by `Env`. */
export type McpEdgeAuthEnv = {
  /** digikey JWKS endpoint. Unset ⇒ JWT path cannot verify ⇒ refuses. */
  DIGIKEY_JWKS_URL?: string;
  /** Expected `iss`. Defaults to the deployment's digikey issuer. */
  DIGIKEY_ISSUER?: string;
  /** Expected `aud`. Defaults to the deployment's digikey audience. */
  DIGIKEY_AUDIENCE?: string;
  /**
   * Service binding to this same Worker. The JWKS lives on `key.digithings.ai`,
   * which is served by this Worker, so a plain `fetch` re-enters its own public
   * route and fails — the verification then fails closed and every MCP call
   * 401s. Through the binding the subrequest never leaves the Worker.
   */
  DIGIKEY_SELF?: { fetch(input: string, init?: RequestInit): Promise<Response> };
  /**
   * Read-through cache for the public JWKS. Keys survive a cold digikey, whose
   * first response took 43 s against a 5 s fetch cap — long enough that the
   * verifier gave up before the container answered.
   */
  TENANT_CONFIG?: {
    get(key: string): Promise<string | null>;
    put(key: string, value: string, opts?: { expirationTtl?: number }): Promise<void>;
  };
};

export type McpEdgeAuthResult =
  | { ok: true; via: "key" | "jwt"; scope?: string }
  | {
      ok: false;
      status: 400 | 401 | 403;
      /**
       * Fixed, token-free reason. `missing_scope` and `wildcard_scope` are
       * the 403s; everything else is a 401, except `uninspectable_body`, a 400.
       */
      reason:
        | "no_credential"
        | "invalid_key"
        | "jwks_not_configured"
        | "malformed_token"
        | "unsupported_alg"
        | "unknown_kid"
        | "jwks_unavailable"
        | "bad_signature"
        | "expired"
        | "not_yet_valid"
        | "wrong_issuer"
        | "wrong_audience"
        | "missing_scope"
        | "missing_tenant"
        | "wildcard_scope"
        | "uninspectable_body";
    };

type Header = { alg?: unknown; kid?: unknown; typ?: unknown };

type Claims = {
  iss?: unknown;
  aud?: unknown;
  exp?: unknown;
  nbf?: unknown;
  iat?: unknown;
  scope?: unknown;
  scopes?: unknown;
  tenant_slug?: unknown;
};

type JwksState = { keys: Map<string, CryptoKey>; fetchedAtMs: number };

/**
 * Per-isolate JWKS cache and single-flight. Module scope, so every request
 * handled by one Worker isolate shares it: a per-request JWKS fetch would put
 * digikey in the path of every MCP call and turn a cold digikey into an MCP
 * outage.
 */
let jwksCache: JwksState | null = null;
let jwksInflight: Promise<JwksState | null> | null = null;

/** Test-only: forget the cached JWKS and any in-flight fetch. */
export function _resetMcpEdgeJwksCacheForTests(): void {
  jwksCache = null;
  jwksInflight = null;
}

const RSA_ALG = { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" } as const;

function base64UrlToBytes(value: string): Uint8Array | null {
  const b64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const pad = b64.length % 4 === 0 ? "" : "=".repeat(4 - (b64.length % 4));
  try {
    const bin = atob(b64 + pad);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) out[i] = bin.charCodeAt(i);
    return out;
  } catch {
    return null;
  }
}

function decodeJsonObject(bytes: Uint8Array): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(new TextDecoder().decode(bytes));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    // not JSON
  }
  return null;
}

/**
 * Import one JWKS entry. Anything that is not an RSA signing key is skipped
 * rather than skipped-and-logged: a JWKS that carries an encryption key too is
 * normal and is not an error.
 */
async function importJwk(raw: unknown): Promise<[string, CryptoKey] | null> {
  if (!raw || typeof raw !== "object") return null;
  const jwk = raw as Record<string, unknown>;
  if (jwk.kty !== "RSA") return null;
  if (typeof jwk.kid !== "string" || !jwk.kid) return null;
  if (typeof jwk.n !== "string" || typeof jwk.e !== "string") return null;
  // `use`/`alg` are advisory per RFC 7517 but a key that names itself for
  // encryption or for a different algorithm must not be tried as RS256.
  if (typeof jwk.use === "string" && jwk.use !== "sig") return null;
  if (typeof jwk.alg === "string" && jwk.alg !== "RS256") return null;
  try {
    const key = await crypto.subtle.importKey(
      "jwk",
      { kty: "RSA", n: jwk.n, e: jwk.e, ext: true, alg: "RS256" },
      RSA_ALG,
      false,
      ["verify"],
    );
    return [jwk.kid, key];
  } catch {
    return null;
  }
}

/** Cap on one JWKS fetch, ms. A hung digikey must not hang the MCP request. */
export const MCP_EDGE_JWKS_TIMEOUT_MS = 5_000;

/**
 * KV key holding the last good JWKS. Public keys only — no secret is cached
 * here. Written on every successful fetch and read before any network call, so
 * a cold digikey cannot take MCP down.
 *
 * Rotation: digikey publishes a new key under a new `kid`; the unknown-`kid`
 * path forces one refetch, which overwrites this key. If digikey is
 * unreachable at that moment the call fails closed, and the next successful
 * fetch repairs the cache. There is deliberately no TTL: expiring the key on a
 * timer would re-break every MCP call while digikey sleeps.
 */
export const MCP_EDGE_JWKS_KV_KEY = "digikey-jwks";

type JwksBody = { keys?: unknown };

/** Read the cached JWKS body, or null when absent/unusable. */
async function readCachedJwks(env: McpEdgeAuthEnv): Promise<JwksBody | null> {
  const kv = env.TENANT_CONFIG;
  if (!kv) return null;
  try {
    const raw = await kv.get(MCP_EDGE_JWKS_KV_KEY);
    if (typeof raw !== "string" || !raw.trim()) return null;
    const parsed = JSON.parse(raw) as JwksBody | null;
    return parsed && Array.isArray(parsed.keys) && parsed.keys.length ? parsed : null;
  } catch {
    return null;
  }
}

/** Best-effort cache write. A failure here must not fail verification. */
async function writeCachedJwks(env: McpEdgeAuthEnv, body: JwksBody): Promise<void> {
  const kv = env.TENANT_CONFIG;
  if (!kv) return;
  try {
    await kv.put(MCP_EDGE_JWKS_KV_KEY, JSON.stringify(body));
  } catch {
    // the caller already has usable keys; caching is an optimisation
  }
}

async function fetchJwks(url: string, env: McpEdgeAuthEnv): Promise<JwksState | null> {
  const cached = await readCachedJwks(env);
  const body = cached ?? (await fetchJwksBody(url, env));
  if (!body) return null;
  if (!cached) await writeCachedJwks(env, body);
  const list = body.keys;
  if (!Array.isArray(list)) return null;
  const keys = new Map<string, CryptoKey>();
  for (const entry of list) {
    const imported = await importJwk(entry);
    if (imported) keys.set(imported[0], imported[1]);
  }
  // An empty key set is not a usable JWKS: refuse rather than cache nothing
  // and retry on every request.
  if (!keys.size) return null;
  return { keys, fetchedAtMs: Date.now() };
}

/**
 * One network read of the JWKS. Goes through the service binding when bound:
 * `key.digithings.ai` is this Worker's own route, and fetching it from inside
 * the Worker does not complete.
 */
async function fetchJwksBody(url: string, env: McpEdgeAuthEnv): Promise<JwksBody | null> {
  try {
    const init: RequestInit = {
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(MCP_EDGE_JWKS_TIMEOUT_MS),
    };
    const res = env.DIGIKEY_SELF ? await env.DIGIKEY_SELF.fetch(url, init) : await fetch(url, init);
    if (!res.ok) return null;
    const body = (await res.json()) as JwksBody | null;
    const list = body?.keys;
    if (!Array.isArray(list) || !list.length) return null;
    return body;
  } catch {
    // Network error, timeout, non-JSON body. Caller treats null as "no keys".
    return null;
  }
}

/**
 * The cached key set, or a fetch. `force` skips the TTL — the unknown-`kid`
 * path uses it exactly once per request so a rotation is picked up without
 * waiting out the TTL.
 *
 * Concurrent callers join one in-flight fetch: a burst of requests after a cold
 * start must not produce a burst of JWKS calls.
 */
function getJwks(url: string, force: boolean, env: McpEdgeAuthEnv): Promise<JwksState | null> {
  if (!force && jwksCache && Date.now() - jwksCache.fetchedAtMs < MCP_EDGE_JWKS_TTL_MS) {
    return Promise.resolve(jwksCache);
  }
  if (jwksInflight) return jwksInflight;
  const fetchPromise = fetchJwks(url, env)
    .then((state) => {
      if (state) jwksCache = state;
      jwksInflight = null;
      return state;
    })
    .catch(() => {
      jwksInflight = null;
      return null;
    });
  jwksInflight = fetchPromise;
  return fetchPromise;
}

/** Normalise an issuer/audience for comparison: trimmed, no trailing slash. */
function normalise(value: string): string {
  // String scan, not `/\/+$/`: a trailing-slash regex on a caller-supplied
  // issuer is a polynomial backtracking case (CodeQL js/polynomial-redos).
  let end = value.trim().length;
  const s = value.trim();
  while (end > 0 && s.charCodeAt(end - 1) === 47 /* "/" */) end -= 1;
  return s.slice(0, end);
}

function claimStrings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.filter((v): v is string => typeof v === "string");
  return [];
}

/**
 * The token's granted scopes. digikey issues the OAuth `scope` claim as a
 * space-delimited string (`digikey/jwt_verify.py` accepts that or a `scopes`
 * array), so both spellings are read.
 */
export function tokenScopes(claims: Claims): string[] {
  const fromArray = claimStrings(claims.scopes);
  if (fromArray.length) return fromArray.map((s) => s.trim()).filter(Boolean);
  const fromString = claimStrings(claims.scope);
  return fromString.flatMap((s) => s.split(/\s+/)).map((s) => s.trim()).filter(Boolean);
}

/**
 * Wildcard scope matching, identical to digikey's `scope_grants_required`
 * (`digikey/src/digikey/scopes.py`): `*` grants everything, `mcp:*` grants
 * `mcp` and every `mcp:…` child, and a narrower grant never satisfies a wider
 * requirement.
 */
export function scopeGrants(granted: readonly string[], required: string): boolean {
  if (!required) return false;
  for (const raw of granted) {
    const g = raw.trim();
    if (!g) continue;
    if (g === "*" || g === required) return true;
    if (g.endsWith(":*")) {
      const prefix = g.slice(0, -2);
      if (required === prefix || required.startsWith(`${prefix}:`)) return true;
    }
  }
  return false;
}

type VerifyResult =
  | { ok: true; scopes: string[]; tenant: string }
  | { ok: false; reason: Extract<McpEdgeAuthResult, { ok: false }>["reason"] };

/**
 * Verify a digikey JWT: signature against the JWKS, then `exp`/`nbf`/`iat`,
 * `iss` and `aud`. Scope is checked by the caller because it depends on which
 * server was asked for.
 */
export async function verifyDigikeyJwt(
  token: string,
  env: McpEdgeAuthEnv,
): Promise<VerifyResult> {
  const parts = token.split(".");
  if (parts.length !== 3 || !parts[0] || !parts[1] || !parts[2]) {
    return { ok: false, reason: "malformed_token" };
  }
  const headerBytes = base64UrlToBytes(parts[0]);
  const payloadBytes = base64UrlToBytes(parts[1]);
  const signature = base64UrlToBytes(parts[2]);
  if (!headerBytes || !payloadBytes || !signature) {
    return { ok: false, reason: "malformed_token" };
  }
  const header = decodeJsonObject(headerBytes) as Header | null;
  const claims = decodeJsonObject(payloadBytes) as Claims | null;
  if (!header || !claims) {
    return { ok: false, reason: "malformed_token" };
  }
  // Only RS256. This is the algorithm digikey signs with, and it is the only
  // one whose public half this verifier can import. Pinning it rejects `none`
  // and every HMAC confusion attempt before any key is looked up.
  if (header.alg !== "RS256") {
    return { ok: false, reason: "unsupported_alg" };
  }
  if (typeof header.kid !== "string" || !header.kid) {
    return { ok: false, reason: "malformed_token" };
  }

  const jwksUrl = env.DIGIKEY_JWKS_URL?.trim() ?? "";
  if (!jwksUrl) {
    return { ok: false, reason: "jwks_not_configured" };
  }

  let state = await getJwks(jwksUrl, false, env);
  if (!state) return { ok: false, reason: "jwks_unavailable" };

  let key = state.keys.get(header.kid);
  if (!key) {
    // Unknown kid: the one refetch that makes rotation work without waiting
    // out the TTL. If the refetch cannot run, the key stays unknown and the
    // request is refused — never allowed on the strength of a failed fetch.
    const refreshed = await getJwks(jwksUrl, true, env);
    if (!refreshed) return { ok: false, reason: "jwks_unavailable" };
    state = refreshed;
    key = state.keys.get(header.kid);
    if (!key) return { ok: false, reason: "unknown_kid" };
  }

  let valid = false;
  try {
    valid = await crypto.subtle.verify(
      RSA_ALG,
      key,
      signature as unknown as ArrayBuffer,
      new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
    );
  } catch {
    valid = false;
  }
  if (!valid) return { ok: false, reason: "bad_signature" };

  const nowSec = Math.floor(Date.now() / 1000);
  const skew = MCP_EDGE_CLOCK_SKEW_SEC;
  // `exp` is required: a digikey token always carries one, and a token without
  // it would be valid forever, which is the opposite of what a short-lived
  // identity is for.
  if (typeof claims.exp !== "number" || !Number.isFinite(claims.exp)) {
    return { ok: false, reason: "malformed_token" };
  }
  if (claims.exp + skew <= nowSec) return { ok: false, reason: "expired" };
  for (const bound of [claims.nbf, claims.iat]) {
    if (typeof bound === "number" && Number.isFinite(bound) && bound - skew > nowSec) {
      return { ok: false, reason: "not_yet_valid" };
    }
  }

  const issuer = normalise(env.DIGIKEY_ISSUER?.trim() || "https://key.digithings.ai");
  if (normalise(typeof claims.iss === "string" ? claims.iss : "") !== issuer) {
    return { ok: false, reason: "wrong_issuer" };
  }
  const audience = normalise(env.DIGIKEY_AUDIENCE?.trim() || "digi-ecosystem");
  if (!claimStrings(claims.aud).some((a) => normalise(a) === audience)) {
    return { ok: false, reason: "wrong_audience" };
  }

  const tenant = typeof claims.tenant_slug === "string" ? claims.tenant_slug.trim() : "";
  return { ok: true, scopes: tokenScopes(claims), tenant };
}

/**
 * Compare two secrets without leaking length or prefix position through
 * timing. Lengths differ publicly; the byte loop does not early-return.
 */
function secretMatches(presented: string, expected: string): boolean {
  const a = new TextEncoder().encode(presented);
  const b = new TextEncoder().encode(expected);
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a[i] ^ b[i];
  return diff === 0;
}

/** The decision log line. Never carries the credential or any part of it. */
function logDecision(opts: {
  serverId: string;
  ok: boolean;
  via?: "key" | "jwt";
  status?: number;
  reason?: string;
  scope?: string;
}): void {
  console.log(
    JSON.stringify({
      event: "mcp_edge_auth",
      server: opts.serverId,
      ok: opts.ok,
      via: opts.via ?? null,
      status: opts.status ?? 200,
      reason: opts.reason ?? null,
      scope: opts.scope ?? null,
    }),
  );
}

/**
 * Largest JSON-RPC frame the edge will buffer to look for a write tool. Well
 * above a realistic note body; a frame bigger than this is refused rather than
 * passed uninspected, so "too big to check" can never become "allowed".
 */
export const MCP_EDGE_MAX_INSPECT_BYTES = 8 * 1024 * 1024;

/** One JSON-RPC member of a frame (a single request or one batch element). */
type JsonRpcFrame = { method?: unknown; params?: unknown };

/**
 * The tool names a frame calls, across a single request and a JSON-RPC batch.
 * Anything that is not a `tools/call` contributes nothing. A malformed member
 * contributes nothing either: the MCP server rejects it on its own, so it
 * cannot execute a tool the edge did not see.
 */
function calledToolNames(frame: unknown): string[] {
  const members = Array.isArray(frame) ? frame : [frame];
  const names: string[] = [];
  for (const member of members) {
    if (!member || typeof member !== "object") continue;
    const call = member as JsonRpcFrame;
    if (call.method !== "tools/call") continue;
    if (!call.params || typeof call.params !== "object") continue;
    const name = (call.params as { name?: unknown }).name;
    if (typeof name === "string" && name) names.push(name);
  }
  return names;
}

/**
 * Write scopes the request's tool calls require. `null` means the body could
 * not be inspected (unreadable, oversized, not JSON) and the request must be
 * refused: the whole point is that a write cannot slip past unchecked.
 *
 * Only POST carries JSON-RPC requests; GET opens the SSE stream and DELETE ends
 * the session, neither of which executes a tool.
 */
async function requiredWriteScopesForRequest(
  request: Request,
  serverId: string,
): Promise<string[] | null> {
  if (request.method !== "POST") return [];
  if (!MCP_EDGE_WRITE_SCOPES[serverId]) return [];

  const declared = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declared) && declared > MCP_EDGE_MAX_INSPECT_BYTES) return null;

  let text: string;
  try {
    text = await request.clone().text();
  } catch {
    return null;
  }
  // `text.length` is UTF-16 units, so it can undercount bytes; a bounded
  // overshoot here is harmless, the cap only exists to stop a huge buffer.
  if (text.length > MCP_EDGE_MAX_INSPECT_BYTES) return null;

  let frame: unknown;
  try {
    frame = JSON.parse(text);
  } catch {
    return null;
  }

  const required: string[] = [];
  for (const tool of calledToolNames(frame)) {
    const scope = mcpWriteScopeForTool(serverId, tool);
    if (scope && !required.includes(scope)) required.push(scope);
  }
  return required;
}

/**
 * Authorize one MCP edge request.
 *
 * `expectedKey` is the server's static edge key (`mcpEdgeKeyFor`); pass "" when
 * none is configured, which disables only the key path. An empty `expectedKey`
 * is never treated as "matches anything".
 */
export async function authorizeMcpEdge(opts: {
  request: Request;
  serverId: string;
  expectedKey: string;
  env: McpEdgeAuthEnv;
}): Promise<McpEdgeAuthResult> {
  const { request, serverId, env } = opts;
  const expectedKey = opts.expectedKey.trim();

  const presentedKey = request.headers.get("x-digi-mcp-key")?.trim() ?? "";
  if (expectedKey && presentedKey && secretMatches(presentedKey, expectedKey)) {
    logDecision({ serverId, ok: true, via: "key" });
    return { ok: true, via: "key" };
  }

  const authorization = request.headers.get("authorization")?.trim() ?? "";
  const bearer = /^bearer\s+(\S+)$/i.exec(authorization);
  if (!bearer) {
    // Either no credential at all, or a key that did not match. Both are a
    // 401 and both are logged: a wrong key and a missing one look identical to
    // the caller on purpose.
    const reason = presentedKey && expectedKey ? "invalid_key" : "no_credential";
    logDecision({ serverId, ok: false, status: 401, reason });
    return { ok: false, status: 401, reason };
  }

  const verified = await verifyDigikeyJwt(bearer[1], env);
  if (!verified.ok) {
    logDecision({ serverId, ok: false, status: 401, reason: verified.reason });
    return { ok: false, status: 401, reason: verified.reason };
  }

  // A token with no tenant claim has no tenant for the server to bind its
  // data to: refuse it rather than let the server guess (#6648).
  if (!verified.tenant) {
    logDecision({ serverId, ok: false, status: 401, reason: "missing_tenant" });
    return { ok: false, status: 401, reason: "missing_tenant" };
  }

  // A bare `*` opens every server and every write tool. Only the house may
  // present one here; any other tenant needs the explicit `mcp:<serverId>`
  // (or `mcp:*`) grant (#6648).
  if (
    verified.scopes.some((s) => s.trim() === "*") &&
    !MCP_EDGE_WILDCARD_TENANTS.has(verified.tenant.toLowerCase())
  ) {
    logDecision({ serverId, ok: false, status: 403, reason: "wildcard_scope" });
    return { ok: false, status: 403, reason: "wildcard_scope" };
  }

  const required = mcpScopeForServer(serverId);
  if (!scopeGrants(verified.scopes, required)) {
    // Valid identity, wrong grant: 403, so the caller can tell "not for you"
    // from "your credential is bad".
    logDecision({ serverId, ok: false, status: 403, reason: "missing_scope", scope: required });
    return { ok: false, status: 403, reason: "missing_scope" };
  }

  // `mcp:<serverId>` opens the server but not its mutating tools. The tool name
  // lives in the JSON-RPC body, so a body the edge cannot read is refused: an
  // uninspected frame must never reach a write tool (DIG-5723).
  const writeScopes = await requiredWriteScopesForRequest(request, serverId);
  if (writeScopes === null) {
    logDecision({ serverId, ok: false, status: 400, reason: "uninspectable_body" });
    return { ok: false, status: 400, reason: "uninspectable_body" };
  }
  for (const writeScope of writeScopes) {
    if (!scopeGrants(verified.scopes, writeScope)) {
      logDecision({
        serverId,
        ok: false,
        status: 403,
        reason: "missing_scope",
        scope: writeScope,
      });
      return { ok: false, status: 403, reason: "missing_scope" };
    }
  }

  logDecision({ serverId, ok: true, via: "jwt", scope: required });
  return { ok: true, via: "jwt", scope: required };
}
