/**
 * MCP OAuth 2.1 PKCE for `/mcp` Authenticate (#3736).
 * Server-only — never import from client components (node:crypto + SSRF fetch).
 */

import { createHash, createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { p } from "@/lib/base-path";
import { isAllowedMcpServerUrl } from "@/lib/deploy-config/mcp-servers";

export const MCP_OAUTH_COOKIE = "dc_mcp_oauth";
export const MCP_OAUTH_MESSAGE = "digichat-mcp-oauth";
const STATE_TTL_MS = 10 * 60_000;

export type OAuthStatePayload = {
  id: string;
  verifier: string;
  tokenEndpoint: string;
  clientId: string;
  clientSecret?: string;
  redirectUri: string;
  nonce: string;
  iat: number;
};

export function pkceVerifier(): string {
  return randomBytes(32).toString("base64url");
}

export function pkceChallenge(verifier: string): string {
  return createHash("sha256").update(verifier).digest("base64url");
}

export function parseResourceMetadataUrl(wwwAuthenticate: string | null): string | null {
  if (!wwwAuthenticate) return null;
  const quoted =
    /(?:resource_metadata|as_uri)\s*=\s*"([^"]+)"/i.exec(wwwAuthenticate);
  if (quoted?.[1]) return quoted[1];
  const bare = /(?:resource_metadata|as_uri)\s*=\s*([^\s,]+)/i.exec(wwwAuthenticate);
  return bare?.[1] ?? null;
}

const MAX_HOPS = 4;

/** SSRF-safe fetch: refuse blocked hosts and do not follow redirects to them. */
export async function ssrfFetch(
  url: string,
  init: RequestInit,
  fetchImpl: typeof fetch = fetch,
  timeoutMs = 10_000,
): Promise<Response> {
  let current = url;
  for (let hop = 0; hop < MAX_HOPS; hop++) {
    if (!isAllowedMcpServerUrl(current)) {
      throw new Error("blocked_url");
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetchImpl(current, {
        ...init,
        redirect: "manual",
        signal: controller.signal,
      });
      if (res.status >= 300 && res.status < 400) {
        const loc = res.headers.get("location");
        if (!loc) throw new Error("redirect_without_location");
        current = new URL(loc, current).toString();
        continue;
      }
      return res;
    } finally {
      clearTimeout(timeout);
    }
  }
  throw new Error("too_many_redirects");
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

async function readJson(res: Response): Promise<Record<string, unknown> | null> {
  try {
    return asRecord(await res.json());
  } catch {
    return null;
  }
}

export type DiscoveredAuth = {
  authorizationEndpoint: string;
  tokenEndpoint: string;
  registrationEndpoint?: string;
};

async function fetchJsonAllowed(
  url: string,
  fetchImpl: typeof fetch,
): Promise<Record<string, unknown> | null> {
  const res = await ssrfFetch(url, { headers: { accept: "application/json" } }, fetchImpl);
  if (!res.ok) return null;
  return readJson(res);
}

export async function discoverMcpAuthorization(
  resourceUrl: string,
  fetchImpl: typeof fetch = fetch,
): Promise<DiscoveredAuth> {
  if (!isAllowedMcpServerUrl(resourceUrl)) {
    throw new Error("blocked_url");
  }
  const resource = new URL(resourceUrl);
  const wellKnown = [
    new URL("/.well-known/oauth-protected-resource", resource.origin).toString(),
    new URL(
      `/.well-known/oauth-protected-resource${resource.pathname}`.replace(/\/$/, ""),
      resource.origin,
    ).toString(),
  ];
  let prm: Record<string, unknown> | null = null;
  for (const u of wellKnown) {
    prm = await fetchJsonAllowed(u, fetchImpl);
    if (prm) break;
  }
  if (!prm) {
    const probe = await ssrfFetch(resourceUrl, { headers: { accept: "application/json" } }, fetchImpl);
    const meta = parseResourceMetadataUrl(probe.headers.get("www-authenticate"));
    if (meta && isAllowedMcpServerUrl(meta)) {
      prm = await fetchJsonAllowed(meta, fetchImpl);
    }
  }
  const servers = prm?.authorization_servers;
  const issuer =
    Array.isArray(servers) && typeof servers[0] === "string" ? servers[0].trim() : "";
  if (!issuer || !isAllowedMcpServerUrl(issuer)) {
    throw new Error("oauth_metadata_missing");
  }
  const asOrigin = new URL(issuer.endsWith("/") ? issuer : `${issuer}/`);
  const asWellKnown = [
    new URL("/.well-known/oauth-authorization-server", asOrigin.origin).toString(),
    new URL("/.well-known/openid-configuration", asOrigin.origin).toString(),
    `${issuer.replace(/\/$/, "")}/.well-known/oauth-authorization-server`,
  ];
  let asMeta: Record<string, unknown> | null = null;
  for (const u of asWellKnown) {
    asMeta = await fetchJsonAllowed(u, fetchImpl);
    if (asMeta?.authorization_endpoint && asMeta?.token_endpoint) break;
    asMeta = null;
  }
  const authorizationEndpoint = String(asMeta?.authorization_endpoint ?? "").trim();
  const tokenEndpoint = String(asMeta?.token_endpoint ?? "").trim();
  if (!isAllowedMcpServerUrl(authorizationEndpoint) || !isAllowedMcpServerUrl(tokenEndpoint)) {
    throw new Error("oauth_endpoints_blocked");
  }
  const registrationEndpoint = String(asMeta?.registration_endpoint ?? "").trim();
  return {
    authorizationEndpoint,
    tokenEndpoint,
    ...(registrationEndpoint && isAllowedMcpServerUrl(registrationEndpoint)
      ? { registrationEndpoint }
      : {}),
  };
}

export async function registerPublicClient(
  registrationEndpoint: string,
  redirectUri: string,
  fetchImpl: typeof fetch = fetch,
): Promise<{ clientId: string; clientSecret?: string }> {
  const res = await ssrfFetch(
    registrationEndpoint,
    {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({
        client_name: "digichat",
        redirect_uris: [redirectUri],
        grant_types: ["authorization_code"],
        response_types: ["code"],
        token_endpoint_auth_method: "none",
      }),
    },
    fetchImpl,
  );
  if (!res.ok) throw new Error("oauth_register_failed");
  const body = await readJson(res);
  const clientId = String(body?.client_id ?? "").trim();
  if (!clientId) throw new Error("oauth_register_failed");
  const clientSecret = String(body?.client_secret ?? "").trim();
  return { clientId, ...(clientSecret ? { clientSecret } : {}) };
}

export function buildAuthorizationUrl(opts: {
  authorizationEndpoint: string;
  clientId: string;
  redirectUri: string;
  challenge: string;
  nonce: string;
  scopes?: string;
}): string {
  const u = new URL(opts.authorizationEndpoint);
  u.searchParams.set("response_type", "code");
  u.searchParams.set("client_id", opts.clientId);
  u.searchParams.set("redirect_uri", opts.redirectUri);
  u.searchParams.set("code_challenge", opts.challenge);
  u.searchParams.set("code_challenge_method", "S256");
  u.searchParams.set("state", opts.nonce);
  u.searchParams.set("scope", opts.scopes?.trim() || "mcp:tools");
  return u.toString();
}

export function oauthSecret(): string | null {
  return process.env.AUTH_SECRET?.trim() || process.env.NEXTAUTH_SECRET?.trim() || null;
}

export function signOAuthState(payload: OAuthStatePayload, secret: string): string {
  const body = Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
  const sig = createHmac("sha256", secret).update(body).digest("base64url");
  return `${body}.${sig}`;
}

export function verifyOAuthState(raw: string, secret: string): OAuthStatePayload | null {
  const dot = raw.lastIndexOf(".");
  if (dot <= 0) return null;
  const body = raw.slice(0, dot);
  const sig = raw.slice(dot + 1);
  const expected = createHmac("sha256", secret).update(body).digest("base64url");
  const a = Buffer.from(sig);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  try {
    const parsed = JSON.parse(Buffer.from(body, "base64url").toString("utf8")) as OAuthStatePayload;
    if (!parsed?.id || !parsed.verifier || !parsed.nonce || !parsed.tokenEndpoint) return null;
    if (Date.now() - payloadIat(parsed) > STATE_TTL_MS) return null;
    return parsed;
  } catch {
    return null;
  }
}

function payloadIat(p: OAuthStatePayload): number {
  return typeof p.iat === "number" ? p.iat : 0;
}

export function oauthCookieHeader(value: string, reqUrl: string): string {
  const secure = new URL(reqUrl).protocol === "https:";
  const parts = [
    `${MCP_OAUTH_COOKIE}=${value}`,
    "HttpOnly",
    "SameSite=Lax",
    `Path=${p("/api/mcp/oauth") || "/"}`,
    "Max-Age=600",
  ];
  if (secure) parts.push("Secure");
  return parts.join("; ");
}

export function clearOAuthCookieHeader(reqUrl: string): string {
  const secure = new URL(reqUrl).protocol === "https:";
  const parts = [
    `${MCP_OAUTH_COOKIE}=`,
    "HttpOnly",
    "SameSite=Lax",
    `Path=${p("/api/mcp/oauth") || "/"}`,
    "Max-Age=0",
  ];
  if (secure) parts.push("Secure");
  return parts.join("; ");
}

export function readOAuthCookie(req: Request): string | null {
  const raw = req.headers.get("cookie") ?? "";
  for (const part of raw.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k === MCP_OAUTH_COOKIE) return rest.join("=");
  }
  return null;
}

export function callbackHtml(opts: {
  origin: string;
  id: string;
  accessToken?: string;
  error?: string;
}): string {
  const msg = {
    type: MCP_OAUTH_MESSAGE,
    id: opts.id,
    ...(opts.accessToken ? { accessToken: opts.accessToken } : {}),
    ...(opts.error ? { error: opts.error } : {}),
  };
  return `<!doctype html><html><body><script>
(function(){
  var msg = ${JSON.stringify(msg)};
  if (window.opener) window.opener.postMessage(msg, ${JSON.stringify(opts.origin)});
  window.close();
})();
</script><p>You can close this window.</p></body></html>`;
}

export function oauthRedirectUri(reqUrl: string): string {
  const origin = new URL(reqUrl).origin;
  return `${origin}${p("/api/mcp/oauth/callback")}`;
}

export async function exchangeAuthorizationCode(
  state: OAuthStatePayload,
  code: string,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    redirect_uri: state.redirectUri,
    code_verifier: state.verifier,
    client_id: state.clientId,
  });
  if (state.clientSecret) body.set("client_secret", state.clientSecret);
  const res = await ssrfFetch(
    state.tokenEndpoint,
    {
      method: "POST",
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        accept: "application/json",
      },
      body,
    },
    fetchImpl,
  );
  if (!res.ok) throw new Error("oauth_token_failed");
  const json = await readJson(res);
  const token = String(json?.access_token ?? "").trim();
  if (!token) throw new Error("oauth_token_missing");
  return token;
}
