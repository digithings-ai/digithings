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
 * server's scope is 403. That distinction is what lets a caller tell "get a
 * token" from "you were not granted this server".
 *
 * Never log the token, a prefix of it, or the key. The decision log carries the
 * server id, which credential path won, the scope and a fixed reason string.
 */

/** Scope each edge server requires. One entry per `MCP_EDGE_SERVERS` id. */
export const MCP_EDGE_SCOPES: Record<string, string> = {
  digisearch: "mcp:digisearch",
  digivault: "mcp:digivault",
};

/** The scope a caller must hold to reach `serverId`, or "" when unmapped. */
export function mcpScopeForServer(serverId: string): string {
  return MCP_EDGE_SCOPES[serverId] ?? "";
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
};

export type McpEdgeAuthResult =
  | { ok: true; via: "key" | "jwt"; scope?: string }
  | {
      ok: false;
      status: 401 | 403;
      /**
       * Fixed, token-free reason. `missing_scope` is the only 403; everything
       * else is a 401.
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
        | "missing_scope";
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

async function fetchJwks(url: string): Promise<JwksState | null> {
  try {
    const res = await fetch(url, {
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(MCP_EDGE_JWKS_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    const body: unknown = await res.json();
    const list = (body as { keys?: unknown } | null)?.keys;
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
function getJwks(url: string, force: boolean): Promise<JwksState | null> {
  if (!force && jwksCache && Date.now() - jwksCache.fetchedAtMs < MCP_EDGE_JWKS_TTL_MS) {
    return Promise.resolve(jwksCache);
  }
  if (jwksInflight) return jwksInflight;
  const fetchPromise = fetchJwks(url)
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
  return value.trim().replace(/\/+$/, "");
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
  | { ok: true; scopes: string[] }
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

  let state = await getJwks(jwksUrl, false);
  if (!state) return { ok: false, reason: "jwks_unavailable" };

  let key = state.keys.get(header.kid);
  if (!key) {
    // Unknown kid: the one refetch that makes rotation work without waiting
    // out the TTL. If the refetch cannot run, the key stays unknown and the
    // request is refused — never allowed on the strength of a failed fetch.
    const refreshed = await getJwks(jwksUrl, true);
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

  return { ok: true, scopes: tokenScopes(claims) };
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

  const required = mcpScopeForServer(serverId);
  if (!scopeGrants(verified.scopes, required)) {
    // Valid identity, wrong grant: 403, so the caller can tell "not for you"
    // from "your credential is bad".
    logDecision({ serverId, ok: false, status: 403, reason: "missing_scope", scope: required });
    return { ok: false, status: 403, reason: "missing_scope" };
  }

  logDecision({ serverId, ok: true, via: "jwt", scope: required });
  return { ok: true, via: "jwt", scope: required };
}
