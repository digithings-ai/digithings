/**
 * Who may reach the helpdesk MCP endpoint (/api/mcp/zammad*), DIG-3585.
 *
 * Until now the only credential was one shared edge key (`ZAMMAD_EDGE_KEY`,
 * sent as `x-digi-mcp-key`). A shared string has no identity: anything that
 * holds it reaches the helpdesk tools from anywhere, inside the invite link or
 * not. This module adds the credential the invite-gated tenant's chat already
 * uses for digisearch and digivault — a short-lived digikey JWT minted
 * server-side by the chat — and a flag that turns the shared key off.
 *
 * Accepted credentials:
 *
 * 1. The edge key, exactly as before (`evaluateMcpGate`). REFUSED when
 *    `ZAMMAD_MCP_JWT_ONLY` is "1": that flag is what closes the shared-key
 *    route once the tenant row has moved to the JWT.
 * 2. `Authorization: Bearer <digikey JWT>`, RS256 against the digikey JWKS,
 *    with `iss`, `aud`, `exp`/`nbf`, and:
 *    - the exact scope `mcp:zammad` (no wildcard: `*` or `mcp:*` do not open
 *      it, so an admin key cannot wander in by accident), and
 *    - a chat principal (`api_key` or `bff_session`); a `bff_session` token
 *      must also name an invite-gated tenant.
 *
 * The chat asks for `mcp:zammad` only on the invite-gated tenant's turn
 * (`mcpEdgeScopeForTenant` in apps/digichat/src/lib/mcp-edge-token.ts), and
 * that turn exists only behind the invite link (occ-gate.ts binds it). So with
 * the flag on, the endpoint answers only that chat.
 *
 * Fail closed everywhere: no JWKS, an unreachable JWKS, an unknown kid after
 * one refetch, a bad signature or a missing claim all refuse. Never log the
 * token, the key, or any part of either.
 */
import { evaluateMcpGate, MCP_KEY_HEADER } from "./mcp-gate";
import { containerLocalMcpPath } from "./paths";

/** The flag that refuses the shared edge key on this endpoint. */
export const HELPDESK_MCP_JWT_ONLY_VAR = "ZAMMAD_MCP_JWT_ONLY";

/** The one scope that opens the endpoint. Exact match only. */
export const HELPDESK_MCP_SCOPE = "mcp:zammad";

/**
 * Tenants whose chat may reach the helpdesk MCP with a bff_session token.
 * Mirrors the values of digichat's `INVITE_ONLY_EMBED_HOSTS`
 * (apps/digichat/src/lib/embed-invite-only.ts); helpdesk-mcp-auth.test.ts
 * holds the two together.
 */
export const HELPDESK_MCP_TENANTS: ReadonlySet<string> = new Set(["occ"]);

/** Principals the chat mints with. Anything else is refused. */
const CHAT_PRINCIPALS: ReadonlySet<string> = new Set(["api_key", "bff_session"]);

export const DEFAULT_DIGIKEY_JWKS_URL = "https://key.digithings.ai/.well-known/jwks.json";
export const DEFAULT_DIGIKEY_ISSUER = "https://key.digithings.ai";
export const DEFAULT_DIGIKEY_AUDIENCE = "digi-ecosystem";

/** How long a fetched JWKS is trusted (digikey's own cache default). */
export const HELPDESK_JWKS_TTL_MS = 5 * 60_000;
/** Cap on one JWKS fetch. A hung digikey must not hang the MCP request. */
export const HELPDESK_JWKS_TIMEOUT_MS = 10_000;
/** Tolerated clock difference on exp/nbf/iat, seconds. */
export const HELPDESK_CLOCK_SKEW_SEC = 60;

type Fetcher = { fetch(input: string, init?: RequestInit): Promise<Response> };

/** The Worker env slice this module reads. Structurally satisfied by `Env`. */
export type HelpdeskMcpEnv = {
  ZAMMAD_EDGE_KEY?: string;
  ZAMMAD_MCP_JWT_ONLY?: string;
  /**
   * Service binding to the Worker that serves digikey. `key.digithings.ai` is
   * another Worker on this zone, and a binding keeps the JWKS read inside
   * Cloudflare. Unbound ⇒ a plain fetch of the public JWKS URL.
   */
  DIGIKEY?: Fetcher;
};

export type HelpdeskMcpGate =
  | { kind: "not-mcp" }
  | { kind: "authorized"; via: "key" | "jwt" }
  | { kind: "unauthorized"; status: 401 | 403; reason: HelpdeskRefusal };

export type HelpdeskRefusal =
  | "no_credential"
  | "invalid_key"
  | "static_key_refused"
  | "malformed_token"
  | "unsupported_alg"
  | "jwks_unavailable"
  | "unknown_kid"
  | "bad_signature"
  | "expired"
  | "not_yet_valid"
  | "wrong_issuer"
  | "wrong_audience"
  | "missing_scope"
  | "wrong_principal"
  | "wrong_tenant";

export type HelpdeskMcpOptions = {
  jwksUrl?: string;
  issuer?: string;
  audience?: string;
  tenants?: ReadonlySet<string>;
  /** Test seam for the JWKS read. */
  fetchJwks?: (url: string, init: RequestInit) => Promise<Response>;
};

/** True when the flag that refuses the shared key is on. */
export function helpdeskJwtOnly(env: HelpdeskMcpEnv): boolean {
  return (env.ZAMMAD_MCP_JWT_ONLY ?? "").trim() === "1";
}

type JwksState = { keys: Map<string, CryptoKey>; fetchedAtMs: number; url: string };
let jwksCache: JwksState | null = null;

/** Test-only: forget the cached JWKS. */
export function _resetHelpdeskJwksCacheForTests(): void {
  jwksCache = null;
}

const RSA_ALG = { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" } as const;

function b64urlBytes(value: string): Uint8Array | null {
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

function jsonObject(bytes: Uint8Array | null): Record<string, unknown> | null {
  if (!bytes) return null;
  try {
    const parsed: unknown = JSON.parse(new TextDecoder().decode(bytes));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

async function importJwk(raw: unknown): Promise<[string, CryptoKey] | null> {
  if (!raw || typeof raw !== "object") return null;
  const jwk = raw as Record<string, unknown>;
  if (jwk.kty !== "RSA" || typeof jwk.kid !== "string" || !jwk.kid) return null;
  if (typeof jwk.n !== "string" || typeof jwk.e !== "string") return null;
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

async function loadJwks(
  url: string,
  env: HelpdeskMcpEnv,
  opts: HelpdeskMcpOptions,
): Promise<JwksState | null> {
  try {
    const init: RequestInit = {
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(HELPDESK_JWKS_TIMEOUT_MS),
    };
    const res = opts.fetchJwks
      ? await opts.fetchJwks(url, init)
      : env.DIGIKEY
        ? await env.DIGIKEY.fetch(url, init)
        : await fetch(url, init);
    if (!res.ok) return null;
    const body = (await res.json()) as { keys?: unknown } | null;
    if (!body || !Array.isArray(body.keys)) return null;
    const keys = new Map<string, CryptoKey>();
    for (const entry of body.keys) {
      const imported = await importJwk(entry);
      if (imported) keys.set(imported[0], imported[1]);
    }
    return keys.size ? { keys, fetchedAtMs: Date.now(), url } : null;
  } catch {
    return null;
  }
}

async function jwks(
  url: string,
  force: boolean,
  env: HelpdeskMcpEnv,
  opts: HelpdeskMcpOptions,
): Promise<JwksState | null> {
  const fresh =
    jwksCache && jwksCache.url === url && Date.now() - jwksCache.fetchedAtMs < HELPDESK_JWKS_TTL_MS;
  if (!force && fresh) return jwksCache;
  const state = await loadJwks(url, env, opts);
  if (state) jwksCache = state;
  return state;
}

function trimSlash(value: string): string {
  let end = value.length;
  while (end > 0 && value.charCodeAt(end - 1) === 47) end -= 1;
  return value.slice(0, end);
}

function strings(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.filter((v): v is string => typeof v === "string");
  return [];
}

/** Granted scopes: the `scopes` array, else the space-delimited `scope` claim. */
function scopesOf(claims: Record<string, unknown>): string[] {
  const list = strings(claims.scopes);
  const raw = list.length ? list : strings(claims.scope).flatMap((s) => s.split(/\s+/));
  return raw.map((s) => s.trim()).filter(Boolean);
}

type Verified = { ok: true } | { ok: false; status: 401 | 403; reason: HelpdeskRefusal };

/** Verify one bearer token for the helpdesk endpoint. */
export async function verifyHelpdeskToken(
  token: string,
  env: HelpdeskMcpEnv,
  opts: HelpdeskMcpOptions = {},
): Promise<Verified> {
  const parts = token.split(".");
  if (parts.length !== 3 || !parts[0] || !parts[1] || !parts[2]) {
    return { ok: false, status: 401, reason: "malformed_token" };
  }
  const header = jsonObject(b64urlBytes(parts[0]));
  const claims = jsonObject(b64urlBytes(parts[1]));
  const signature = b64urlBytes(parts[2]);
  if (!header || !claims || !signature) {
    return { ok: false, status: 401, reason: "malformed_token" };
  }
  // RS256 only: rejects `none` and HMAC confusion before any key is looked up.
  if (header.alg !== "RS256") return { ok: false, status: 401, reason: "unsupported_alg" };
  if (typeof header.kid !== "string" || !header.kid) {
    return { ok: false, status: 401, reason: "malformed_token" };
  }

  const url = (opts.jwksUrl ?? DEFAULT_DIGIKEY_JWKS_URL).trim();
  let state = await jwks(url, false, env, opts);
  if (!state) return { ok: false, status: 401, reason: "jwks_unavailable" };
  let key = state.keys.get(header.kid);
  if (!key) {
    // One refetch, so a rotated key is picked up without waiting out the TTL.
    state = await jwks(url, true, env, opts);
    if (!state) return { ok: false, status: 401, reason: "jwks_unavailable" };
    key = state.keys.get(header.kid);
    if (!key) return { ok: false, status: 401, reason: "unknown_kid" };
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
  if (!valid) return { ok: false, status: 401, reason: "bad_signature" };

  const now = Math.floor(Date.now() / 1000);
  if (typeof claims.exp !== "number" || !Number.isFinite(claims.exp)) {
    return { ok: false, status: 401, reason: "malformed_token" };
  }
  if (claims.exp + HELPDESK_CLOCK_SKEW_SEC <= now) {
    return { ok: false, status: 401, reason: "expired" };
  }
  for (const bound of [claims.nbf, claims.iat]) {
    if (
      typeof bound === "number" &&
      Number.isFinite(bound) &&
      bound - HELPDESK_CLOCK_SKEW_SEC > now
    ) {
      return { ok: false, status: 401, reason: "not_yet_valid" };
    }
  }
  const issuer = trimSlash((opts.issuer ?? DEFAULT_DIGIKEY_ISSUER).trim());
  if (trimSlash(typeof claims.iss === "string" ? claims.iss.trim() : "") !== issuer) {
    return { ok: false, status: 401, reason: "wrong_issuer" };
  }
  const audience = trimSlash((opts.audience ?? DEFAULT_DIGIKEY_AUDIENCE).trim());
  if (!strings(claims.aud).some((a) => trimSlash(a.trim()) === audience)) {
    return { ok: false, status: 401, reason: "wrong_audience" };
  }

  // A valid identity from here on: refusals are 403 ("not for you").
  if (!scopesOf(claims).includes(HELPDESK_MCP_SCOPE)) {
    return { ok: false, status: 403, reason: "missing_scope" };
  }
  const principal = typeof claims.principal_kind === "string" ? claims.principal_kind : "";
  if (!CHAT_PRINCIPALS.has(principal)) {
    return { ok: false, status: 403, reason: "wrong_principal" };
  }
  if (principal === "bff_session") {
    const tenants = opts.tenants ?? HELPDESK_MCP_TENANTS;
    const tenant = typeof claims.tenant_slug === "string" ? claims.tenant_slug.trim() : "";
    if (!tenant || !tenants.has(tenant)) {
      return { ok: false, status: 403, reason: "wrong_tenant" };
    }
  }
  return { ok: true };
}

function logDecision(
  ok: boolean,
  detail: { via?: string; status?: number; reason?: string },
): void {
  // Fixed fields only: never the token, the key, or any part of either.
  console.log(JSON.stringify({ event: "helpdesk_mcp_auth", ok, ...detail }));
}

/**
 * The edge verdict for one request to the helpdesk MCP endpoint.
 *
 * Not an MCP path ⇒ "not-mcp" and the caller routes as usual.
 */
export async function authorizeHelpdeskMcp(
  request: Request,
  pathname: string,
  env: HelpdeskMcpEnv,
  opts: HelpdeskMcpOptions = {},
): Promise<HelpdeskMcpGate> {
  if (containerLocalMcpPath(pathname) === null) return { kind: "not-mcp" };
  const jwtOnly = helpdeskJwtOnly(env);
  const presentedKey = request.headers.get(MCP_KEY_HEADER);

  if (!jwtOnly) {
    // The shared key, unchanged and executed by the same gate as before.
    const keyGate = evaluateMcpGate(pathname, presentedKey, env.ZAMMAD_EDGE_KEY);
    if (keyGate.kind === "authorized") {
      logDecision(true, { via: "key" });
      return { kind: "authorized", via: "key" };
    }
  }

  const bearer = /^bearer\s+(\S+)$/i.exec(request.headers.get("authorization")?.trim() ?? "");
  if (!bearer) {
    const reason: HelpdeskRefusal = presentedKey?.trim()
      ? jwtOnly
        ? "static_key_refused"
        : "invalid_key"
      : "no_credential";
    logDecision(false, { status: 401, reason });
    return { kind: "unauthorized", status: 401, reason };
  }

  const verified = await verifyHelpdeskToken(bearer[1]!, env, opts);
  if (!verified.ok) {
    logDecision(false, { status: verified.status, reason: verified.reason });
    return { kind: "unauthorized", status: verified.status, reason: verified.reason };
  }
  logDecision(true, { via: "jwt" });
  return { kind: "authorized", via: "jwt" };
}
