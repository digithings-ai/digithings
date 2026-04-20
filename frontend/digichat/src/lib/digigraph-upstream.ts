import {
  exchangeDigikeyApiKey,
  exchangeDigikeyBffSession,
  isDigikeyApiKeyMaterial,
} from "@/lib/digikey-exchange";

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

/**
 * JWT + optional LiteLLM proxy key (DigiKey token exchange or static bootstrap key).
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
      const ex = await exchangeDigikeyApiKey(digikeyUrl, raw);
      if (ex)
        return { bearer: ex.accessToken, litellmProxyApiKey: ex.litellmProxyApiKey };
      throw new DigigraphUpstreamAuthError(
        "DigiKey api_key exchange failed (check DigiKey /v1/oauth/token and key material)."
      );
    }
  }

  if (digikeyUrl && bffTok && tenantSlug && ownerUserSub) {
    const ex = await exchangeDigikeyBffSession(
      digikeyUrl,
      bffTok,
      tenantSlug,
      ownerUserSub
    );
    if (ex)
      return { bearer: ex.accessToken, litellmProxyApiKey: ex.litellmProxyApiKey };
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
