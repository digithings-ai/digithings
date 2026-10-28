/**
 * The digithings chat's own identity at the MCP edge.
 *
 * The chat does not dial digisearch/digivault itself: it hands digigraph a row
 * per MCP server (`X-Digi-Mcp-Servers`), and digigraph sends that row's `token`
 * as `Authorization: Bearer <token>` (`digigraph/orchestration/mcp_client.py`,
 * `mcp_http_headers`). So this module's job is one thing: mint a digikey JWT
 * carrying `mcp:<serverId>` for the servers the deployment marks
 * `authScheme: jwt`, server-side, and put it on the row.
 *
 * Why an identity at all: the edge used to accept one shared static string, so
 * every caller could reach every server, and rotating one caller's access was
 * not possible. A JWT carries `mcp:digisearch` or `mcp:digivault` and nothing
 * else survives at the edge — a public-domain tenant configured with digisearch
 * alone is refused at digivault with 403 by the Worker, not by convention here.
 *
 * Server-side only, per the BFF rule in apps/digichat/AGENTS.md: the token is
 * minted in the route handler, never projected to the browser. Nothing here
 * writes the token to a log, an error message or a client payload.
 *
 * Credential precedence:
 *
 * 1. `DIGICHAT_MCP_IDENTITY_KEY` when it is digikey API-key material
 *    (`dgk_live_…`) — a dedicated identity whose scopes are its own, which is
 *    the tightest form of "the chat's own identity".
 * 2. the existing BFF credential (`DIGIKEY_BFF_TOKEN` + `DIGIKEY_URL`), the
 *    same exchange digichat already uses for digigraph.
 *
 * Both go through `digikey-exchange.ts`; both request explicit
 * `requested_scopes`, so the minted token is narrower than the credential.
 */
import { BoundedTTLMap } from "@/lib/bounded-map";
import {
  exchangeDigikeyApiKey,
  exchangeDigikeyBffSession,
  isDigikeyApiKeyMaterial,
} from "@/lib/digikey-exchange";
import type { McpUpstreamServer } from "@/lib/deploy-config/mcp-servers";
import { jwtExpiresAtMs } from "@/lib/digigraph-upstream";
import { isInviteOnlyDeployment } from "@/lib/embed-invite-only";

/** Every edge server scope the chat may request. Mirrors the Worker's set. */
export const MCP_EDGE_SCOPES: Record<string, string> = {
  digisearch: "mcp:digisearch",
  digivault: "mcp:digivault",
};

/**
 * A requested scope must be one of the known per-server scopes. This is a
 * fail-closed allowlist, not a formality: `requested_scopes` reaches digikey,
 * and a value interpolated from config must not be able to ask for `*` or an
 * unrelated component's scope.
 */
const SCOPE_RE = /^mcp:[a-z0-9][a-z0-9-]{0,63}$/;

/** The scope for an MCP server id, or "" when it has none. */
export function mcpEdgeScopeFor(serverId: string): string {
  return MCP_EDGE_SCOPES[serverId.trim().toLowerCase()] ?? "";
}

/**
 * The scope `serverId` may be minted for on `tenantSlug`'s turn, or "".
 *
 * The shared servers (`MCP_EDGE_SCOPES`) keep their scope on every tenant.
 * Any other `authScheme: jwt` row is a tenant-private server, and it gets
 * `mcp:<id>` ONLY on an invite-gated tenant's turn (DIG-3585). That turn exists
 * only behind the invite link (the chat Worker binds it from the invite cookie
 * and drops the client's own tenant headers), so a private server's edge can
 * require that exact scope and know which chat is calling. On every other
 * tenant such a row gets no scope, so no token is ever asked for.
 *
 * Rows come from operator documents only (tenant KV / deploy YAML), never from
 * a session overlay: the overlay is checked against `allowUserServers` and its
 * rows cannot set `authScheme`.
 */
export function mcpEdgeScopeForTenant(
  serverId: string,
  tenantSlug: string | null | undefined,
): string {
  const shared = mcpEdgeScopeFor(serverId);
  if (shared) return shared;
  if (!isInviteOnlyDeployment(null, tenantSlug ?? null)) return "";
  const scope = `mcp:${serverId.trim().toLowerCase()}`;
  return SCOPE_RE.test(scope) ? scope : "";
}

/** Minted tokens are reused until this long before their `exp`. */
export const MCP_EDGE_TOKEN_EXPIRY_SKEW_MS = 60_000;

export type McpEdgeIdentity = {
  /** digikey base URL (`DIGIKEY_URL`). */
  digikeyUrl: string;
  /** BFF credential (`DIGIKEY_BFF_TOKEN`). */
  bffToken?: string;
  /** Dedicated API-key identity (`DIGICHAT_MCP_IDENTITY_KEY`), if configured. */
  apiKey?: string;
  tenantSlug: string;
  subject: string;
};

/** Read the identity the container is configured with. No secret is required. */
export function readMcpEdgeIdentityFromEnv(
  tenantSlug: string,
  subject: string,
): McpEdgeIdentity | null {
  const digikeyUrl = process.env.DIGIKEY_URL?.trim();
  if (!digikeyUrl) return null;
  const apiKey = process.env.DIGICHAT_MCP_IDENTITY_KEY?.trim();
  const bffToken = process.env.DIGIKEY_BFF_TOKEN?.trim();
  if (!apiKey && !bffToken) return null;
  return {
    digikeyUrl,
    ...(apiKey ? { apiKey } : {}),
    ...(bffToken ? { bffToken } : {}),
    tenantSlug,
    subject,
  };
}

export type McpEdgeTokenOutcome =
  | { ok: true; token: string }
  | { ok: false; reason: "no_identity" | "rejected" | "unreachable" | "bad_scope" };

type CacheEntry = { token: string; expiresAtMs: number };

/**
 * Minted tokens, keyed by identity and scope set. Bounded and TTL'd: a stale
 * entry must never outlive its token, and an unbounded map keyed by tenant is
 * a slow leak on a long-lived container.
 *
 * The key holds no credential material — tenant, subject and the scopes are
 * enough, because one container runs one identity for many tenants.
 */
const tokenCache = new BoundedTTLMap<string, CacheEntry>(500, 15 * 60_000);

/** Test-only: clear the minted-token cache. */
export function _resetMcpEdgeTokenCacheForTests(): void {
  tokenCache.clear();
}

function cacheKeyFor(identity: McpEdgeIdentity, scopes: readonly string[]): string {
  return [identity.tenantSlug, identity.subject, ...scopes].join("|");
}

function storeToken(key: string, token: string): McpEdgeTokenOutcome {
  const exp = jwtExpiresAtMs(token);
  const expiresAtMs = exp === null ? Date.now() + 5 * 60_000 : exp - MCP_EDGE_TOKEN_EXPIRY_SKEW_MS;
  const ttlMs = Math.max(60_000, expiresAtMs - Date.now());
  tokenCache.set(key, { token, expiresAtMs }, ttlMs);
  return { ok: true, token };
}

/**
 * Mint (or reuse) a digikey JWT for `scopes`.
 *
 * Reuse is per scope set: digisearch-only and digisearch+digivault are two
 * tokens, so a tenant that drops a server does not keep carrying its scope.
 */
export async function mintMcpEdgeToken(opts: {
  identity: McpEdgeIdentity | null;
  scopes: readonly string[];
}): Promise<McpEdgeTokenOutcome> {
  const { identity } = opts;
  if (!identity) return { ok: false, reason: "no_identity" };

  const scopes = [...new Set(opts.scopes.map((s) => s.trim()).filter(Boolean))].sort();
  if (!scopes.length) return { ok: false, reason: "bad_scope" };
  // Unknown scopes are refused whole, not filtered: a caller that asked for
  // something the deployment does not grant should not silently get less.
  if (!scopes.every((s) => SCOPE_RE.test(s))) return { ok: false, reason: "bad_scope" };

  const key = cacheKeyFor(identity, scopes);
  const cached = tokenCache.get(key);
  if (cached && cached.expiresAtMs > Date.now()) return { ok: true, token: cached.token };

  const apiKey = identity.apiKey?.trim() ?? "";
  if (apiKey && isDigikeyApiKeyMaterial(apiKey)) {
    try {
      const exchange = await exchangeDigikeyApiKey(identity.digikeyUrl, apiKey, scopes);
      if (!exchange) return { ok: false, reason: "rejected" };
      return storeToken(key, exchange.accessToken);
    } catch {
      // A thrown fetch (DNS, TLS, abort) is a cold or unreachable digikey. It
      // must not propagate: the caller merges static and jwt rows into ONE
      // header, and letting this throw would drop every server on the turn,
      // including the static ones that need no identity.
      return { ok: false, reason: "unreachable" };
    }
  }

  const bffToken = identity.bffToken?.trim() ?? "";
  if (!bffToken) return { ok: false, reason: "no_identity" };
  const outcome = await exchangeDigikeyBffSession(
    identity.digikeyUrl,
    bffToken,
    identity.tenantSlug,
    identity.subject,
    scopes,
  );
  if (!outcome.ok) {
    return { ok: false, reason: outcome.reason === "unreachable" ? "unreachable" : "rejected" };
  }
  return storeToken(key, outcome.exchange.accessToken);
}

/**
 * Put the chat's JWT on every row the deployment marks `authScheme: jwt`.
 *
 * The minted token wins over a row's static `token`/`authHeader`, and when
 * minting fails the row is left with NO token — it does not fall back to the
 * static key. A fallback would be a silent widening: the edge would accept a
 * credential that reaches every server, for a tenant that asked for scoped
 * access. The turn then fails against that server, which is the visible,
 * correct outcome.
 *
 * `authHeader` is removed on a jwt row so the MCP client's default applies:
 * `Authorization: Bearer <token>`.
 */
export async function withMcpEdgeIdentity(
  servers: readonly McpUpstreamServer[],
  ctx: {
    identity: McpEdgeIdentity | null;
    /** Test seam: lets a caller mint synchronously in a unit test. */
    mint?: typeof mintMcpEdgeToken;
  },
): Promise<McpUpstreamServer[]> {
  const jwtRows = servers.filter((s) => s.authScheme === "jwt");
  if (!jwtRows.length) return servers.map((s) => ({ ...s }));

  // DIG-3585: the shared servers share one token; each tenant-private server
  // gets a token of its own, carrying only its scope. So a private edge never
  // sees a token good for digisearch/digivault, the shared edges never see the
  // private scope, and a digikey refusal of one private scope cannot take the
  // shared servers down with it. A row with no scope gets no token — never a
  // neighbour's.
  const tenantSlug = ctx.identity?.tenantSlug;
  const sharedScopes: string[] = [];
  const privateScopes: string[] = [];
  for (const row of jwtRows) {
    const scope = mcpEdgeScopeForTenant(row.id, tenantSlug);
    if (!scope) continue;
    const bucket = mcpEdgeScopeFor(row.id) ? sharedScopes : privateScopes;
    if (!bucket.includes(scope)) bucket.push(scope);
  }

  const mint = ctx.mint ?? mintMcpEdgeToken;
  const tokens = new Map<string, McpEdgeTokenOutcome>();
  const shared: McpEdgeTokenOutcome = sharedScopes.length
    ? await mint({ identity: ctx.identity, scopes: sharedScopes })
    : { ok: false, reason: "bad_scope" };
  for (const scope of sharedScopes) tokens.set(scope, shared);
  for (const scope of privateScopes) {
    tokens.set(scope, await mint({ identity: ctx.identity, scopes: [scope] }));
  }

  return servers.map((row) => {
    const copy: McpUpstreamServer = { ...row };
    if (row.authScheme !== "jwt") return copy;
    const scope = mcpEdgeScopeForTenant(row.id, tenantSlug);
    const outcome = scope ? tokens.get(scope) : undefined;
    if (outcome?.ok) {
      copy.token = outcome.token;
      delete copy.authHeader;
    } else {
      // Fail closed: no credential at all for this row, never the static one.
      delete copy.token;
      delete copy.authHeader;
    }
    return copy;
  });
}
