import { randomBytes } from "node:crypto";
import { requireDigiChatAuth } from "@/lib/request-auth";
import { isEmbedChatRequest, resolveEmbedChatTenant } from "@/lib/embed-chat-tenant";
import { checkEmbedIpRateLimit } from "@/lib/embed-ip-rate-limit";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";
import {
  operatorMcpServersForUpstream,
  resolveMcpOAuthResourceUrl,
} from "@/lib/deploy-config/mcp-servers";
import {
  getDigichatConfig,
  resolveDeploymentForHost,
} from "@/lib/deploy-config/loader";
import {
  buildAuthorizationUrl,
  discoverMcpAuthorization,
  oauthCookieHeader,
  oauthRedirectUri,
  oauthSecret,
  pkceChallenge,
  pkceVerifier,
  registerPublicClient,
  signOAuthState,
} from "@/lib/mcp-oauth";

export const maxDuration = 30;

function jsonError(message: string, status: number): Response {
  return new Response(JSON.stringify({ ok: false, error: message }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function rateLimitResponse(message: string, retryAfterSec: number): Response {
  return new Response(JSON.stringify({ ok: false, error: message }), {
    status: 429,
    headers: {
      "content-type": "application/json",
      "retry-after": String(retryAfterSec),
    },
  });
}

/**
 * POST /api/mcp/oauth/start — PKCE start for `/mcp` Authenticate.
 * Auth mirrors POST /api/chat (session/machine OR verified embed).
 */
export async function POST(req: Request): Promise<Response> {
  const authResult = await requireDigiChatAuth(req);
  let rateKey: string;
  if (authResult instanceof Response) {
    if (!isEmbedChatRequest(req)) return authResult;
    const embedCtx = resolveEmbedChatTenant(req);
    if (embedCtx instanceof Response) return embedCtx;
    const ipRate = checkEmbedIpRateLimit(req);
    if (!ipRate.allowed) {
      return rateLimitResponse(
        "Too many requests from this address. Try again shortly.",
        ipRate.retryAfterSec,
      );
    }
    rateKey = `mcp-oauth:embed:${embedCtx.tenantSlug}`;
  } else {
    rateKey = `mcp-oauth:${authResult.tenantSlug}:${authResult.ownerUserSub}`;
  }
  const rate = checkBffRateLimit(rateKey, 10);
  if (!rate.allowed) {
    return rateLimitResponse("Too many requests. Try again shortly.", rate.retryAfterSec);
  }

  const secret = oauthSecret();
  if (!secret) return jsonError("OAuth is not configured.", 503);

  let body: unknown;
  try {
    const raw = await req.text();
    if (raw.length > 4096) return jsonError("Request too large.", 413);
    body = raw ? JSON.parse(raw) : {};
  } catch {
    return jsonError("Invalid JSON.", 400);
  }
  const rec = body && typeof body === "object" ? (body as Record<string, unknown>) : {};
  const id = String(rec.id ?? "")
    .trim()
    .toLowerCase();
  if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(id)) {
    return jsonError("id must be a lowercase slug.", 400);
  }
  const clientUrl = String(rec.url ?? "").trim();
  const clientIdExtra = String(rec.client_id ?? "").trim();
  const scopes = String(rec.scopes ?? "").trim();

  const cfg = getDigichatConfig();
  const embedHost = req.headers.get("x-embed-host");
  const dep = resolveDeploymentForHost(embedHost, cfg) ?? cfg.deployment;
  const operator = operatorMcpServersForUpstream(dep);
  const resourceUrl = resolveMcpOAuthResourceUrl({
    operator,
    id,
    clientUrl,
    allowUserServers: dep?.mcp?.allowUserServers === true,
  });
  if (!resourceUrl) {
    return jsonError("MCP URL is missing or not allowed.", 400);
  }

  try {
    const discovered = await discoverMcpAuthorization(resourceUrl);
    const redirectUri = oauthRedirectUri(req.url);
    let clientId = clientIdExtra;
    let clientSecret: string | undefined;
    if (!clientId && discovered.registrationEndpoint) {
      const registered = await registerPublicClient(discovered.registrationEndpoint, redirectUri);
      clientId = registered.clientId;
      clientSecret = registered.clientSecret;
    }
    if (!clientId) {
      return jsonError("Add client_id in the MCP JSON, or use a server that supports DCR.", 400);
    }
    const verifier = pkceVerifier();
    const nonce = randomBytes(16).toString("base64url");
    const authorizationUrl = buildAuthorizationUrl({
      authorizationEndpoint: discovered.authorizationEndpoint,
      clientId,
      redirectUri,
      challenge: pkceChallenge(verifier),
      nonce,
      scopes: scopes || undefined,
    });
    const cookie = signOAuthState(
      {
        id,
        verifier,
        tokenEndpoint: discovered.tokenEndpoint,
        clientId,
        clientSecret,
        redirectUri,
        nonce,
        iat: Date.now(),
      },
      secret,
    );
    return new Response(JSON.stringify({ ok: true, authorizationUrl }), {
      status: 200,
      headers: {
        "content-type": "application/json",
        "set-cookie": oauthCookieHeader(cookie, req.url),
      },
    });
  } catch (e) {
    const message = e instanceof Error ? e.message : "oauth_start_failed";
    if (message === "blocked_url") return jsonError("MCP URL is not allowed.", 400);
    return jsonError("Could not start OAuth for this MCP server.", 502);
  }
}
