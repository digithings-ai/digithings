import {
  exchangeDigikeyApiKey,
  exchangeDigikeyBffSession,
  isDigikeyApiKeyMaterial,
  type DigikeyTokenExchange,
} from "@/lib/digikey-exchange";
import { BoundedTTLMap } from "@/lib/bounded-map";

export class DigigraphUpstreamAuthError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DigigraphUpstreamAuthError";
  }
}

export type DigigraphUpstreamAuth = {
  bearer: string;
  /** From DigiKey ``litellm_proxy_api_key`` when DIGIKEY_LITELLM_PROXY_KEY is set — forward as ``X-LiteLLM-Proxy-Key`` to DigiGraph. */
  litellmProxyApiKey: string | null;
};

type CacheEntry = {
  bearer: string;
  litellmProxyApiKey: string | null;
  expiresAtMs: number;
};

const MAX_UPSTREAM_CACHE_ENTRIES = 2_000;
const _upstreamCache = new BoundedTTLMap<string, CacheEntry>(
  MAX_UPSTREAM_CACHE_ENTRIES,
  30 * 60_000
);
const EXPIRY_SKEW_MS = 60_000;

function jwtExpiresAtMs(token: string): number | null {
  const parts = token.split(".");
  if (parts.length < 2) return null;
  try {
    const payload = JSON.parse(
      Buffer.from(parts[1].replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8")
    ) as { exp?: number };
    if (typeof payload.exp === "number") return payload.exp * 1000;
  } catch {
    return null;
  }
  return null;
}

function cacheExpiryMs(token: string): number {
  const exp = jwtExpiresAtMs(token);
  if (exp) return exp - EXPIRY_SKEW_MS;
  return Date.now() + 5 * 60_000;
}

function readCache(key: string): DigigraphUpstreamAuth | null {
  const hit = _upstreamCache.get(key);
  if (!hit || hit.expiresAtMs <= Date.now()) {
    if (hit) _upstreamCache.delete(key);
    return null;
  }
  return { bearer: hit.bearer, litellmProxyApiKey: hit.litellmProxyApiKey };
}

function writeCache(key: string, ex: DigikeyTokenExchange): DigigraphUpstreamAuth {
  const auth: DigigraphUpstreamAuth = {
    bearer: ex.accessToken,
    litellmProxyApiKey: ex.litellmProxyApiKey,
  };
  const expiresAtMs = cacheExpiryMs(ex.accessToken);
  _upstreamCache.set(
    key,
    { ...auth, expiresAtMs },
    Math.max(60_000, expiresAtMs - Date.now())
  );
  return auth;
}

/** Test-only: reset in-memory upstream JWT cache. */
export function _resetUpstreamAuthCacheForTests(): void {
  _upstreamCache.clear();
}

/**
 * JWT + optional LiteLLM proxy key (DigiKey token exchange or static bootstrap key).
 * Reuses cached JWT until exp minus skew when exchange path is used.
 */
export async function resolveDigigraphUpstreamAuth(
  req: Request,
  tenantSlug: string,
  ownerUserSub: string
): Promise<DigigraphUpstreamAuth> {
  const staticKey = process.env.DIGIGRAPH_UPSTREAM_API_KEY?.trim();
  const digikeyUrl = process.env.DIGIKEY_URL?.trim();
  const bffTok = process.env.DIGIKEY_BFF_TOKEN?.trim();

  const authz = req.headers.get("authorization");
  if (authz?.startsWith("Bearer ") && digikeyUrl) {
    const raw = authz.slice(7).trim();
    if (raw && isDigikeyApiKeyMaterial(raw)) {
      const cacheKey = `api_key:${raw.slice(0, 16)}`;
      const cached = readCache(cacheKey);
      if (cached) return cached;
      const ex = await exchangeDigikeyApiKey(digikeyUrl, raw);
      if (ex) return writeCache(cacheKey, ex);
      throw new DigigraphUpstreamAuthError(
        "DigiKey api_key exchange failed (check DigiKey /v1/oauth/token and key material)."
      );
    }
  }

  if (digikeyUrl && bffTok && tenantSlug && ownerUserSub) {
    const cacheKey = `bff:${tenantSlug}:${ownerUserSub}`;
    const cached = readCache(cacheKey);
    if (cached) return cached;
    const ex = await exchangeDigikeyBffSession(
      digikeyUrl,
      bffTok,
      tenantSlug,
      ownerUserSub
    );
    if (ex) return writeCache(cacheKey, ex);
    throw new DigigraphUpstreamAuthError(
      "DigiKey bff_session exchange failed (check DIGIKEY_BFF_TOKEN and DigiKey configuration)."
    );
  }

  if (staticKey)
    return { bearer: staticKey, litellmProxyApiKey: null };

  if (digikeyUrl && !bffTok) {
    throw new DigigraphUpstreamAuthError(
      "DIGIKEY_URL is set but DIGIKEY_BFF_TOKEN is missing. Copy the same DigiKey secret into DigiChat (see docs/LOCAL_STACK.md), or send Authorization: Bearer dgk_live_…, or set DIGIGRAPH_UPSTREAM_API_KEY."
    );
  }

  throw new DigigraphUpstreamAuthError(
    "Set DIGIKEY_URL + DIGIKEY_BFF_TOKEN (session exchange), or Authorization: Bearer dgk_live_…, or DIGIGRAPH_UPSTREAM_API_KEY."
  );
}

/** @deprecated Prefer resolveDigigraphUpstreamAuth for LiteLLM key forwarding. */
export async function resolveDigigraphUpstreamBearer(
  req: Request,
  tenantSlug: string,
  ownerUserSub: string
): Promise<string> {
  const a = await resolveDigigraphUpstreamAuth(req, tenantSlug, ownerUserSub);
  return a.bearer;
}
