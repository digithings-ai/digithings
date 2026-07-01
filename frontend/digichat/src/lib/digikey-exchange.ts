const DIGIKEY_PREFIX = "dgk_live_";

type TokenJson = {
  access_token?: string;
  litellm_proxy_api_key?: string;
};

export type DigikeyTokenExchange = {
  accessToken: string;
  litellmProxyApiKey: string | null;
};

function parseTokenPayload(data: TokenJson): DigikeyTokenExchange | null {
  const accessToken = data.access_token?.trim();
  if (!accessToken) return null;
  const k = data.litellm_proxy_api_key?.trim();
  return {
    accessToken,
    litellmProxyApiKey: k && k.length ? k : null,
  };
}

/**
 * Exchange a DigiKey-issued API key for a short-lived JWT (Authorization: Bearer … to DigiGraph).
 */
export async function exchangeDigikeyApiKey(
  digikeyBaseUrl: string,
  apiKey: string
): Promise<DigikeyTokenExchange | null> {
  const base = digikeyBaseUrl.replace(/\/$/, "");
  const res = await fetch(`${base}/v1/oauth/token`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ grant_type: "api_key", api_key: apiKey }),
  });
  if (!res.ok) return null;
  const data = (await res.json()) as TokenJson;
  return parseTokenPayload(data);
}

/**
 * OIDC-backed session exchange (DigiChat BFF → DigiKey). Requires DIGIKEY_BFF_TOKEN on DigiKey.
 */
export async function exchangeDigikeyBffSession(
  digikeyBaseUrl: string,
  bffToken: string,
  tenantSlug: string,
  subject: string
): Promise<DigikeyTokenExchange | null> {
  const base = digikeyBaseUrl.replace(/\/$/, "");
  const res = await fetch(`${base}/v1/oauth/token`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      Authorization: `Bearer ${bffToken}`,
    },
    body: JSON.stringify({
      grant_type: "bff_session",
      tenant_slug: tenantSlug,
      subject,
    }),
  });
  if (!res.ok) return null;
  const data = (await res.json()) as TokenJson;
  return parseTokenPayload(data);
}

export function isDigikeyApiKeyMaterial(token: string): boolean {
  return token.startsWith(DIGIKEY_PREFIX);
}

export { DIGIKEY_PREFIX };
