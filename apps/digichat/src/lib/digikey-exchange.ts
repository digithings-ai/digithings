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
 * Exchange a digikey-issued API key for a short-lived JWT (Authorization: Bearer … to digigraph).
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

/** Per-attempt abort window for a single digikey token request. */
export const DIGIKEY_BFF_ATTEMPT_TIMEOUT_MS = 30_000;

/** Backoff waited before each attempt, in ms. The first attempt has no delay. */
export const DIGIKEY_BFF_RETRY_DELAYS_MS = [
  0, 2_000, 4_000, 8_000, 12_000, 15_000, 15_000,
] as const;

/**
 * Overall budget of one `exchangeDigikeyBffSession` call: the whole retry loop
 * is abandoned once this much wall clock has passed. It bounds the loop, not
 * each attempt.
 *
 * It bounds the exchange up to the response headers: the per-attempt abort
 * timer is released when the headers arrive, so a response that then stalls
 * its body is not bounded by this budget.
 *
 * Exported, and pinned by a test, so the number the code enforces and the
 * number the doc claims cannot drift apart.
 */
export const DIGIKEY_BFF_RETRY_BUDGET_MS = 100_000;

/**
 * OIDC-backed session exchange (digichat BFF → digikey). Requires DIGIKEY_BFF_TOKEN on digikey.
 */
export async function exchangeDigikeyBffSession(
  digikeyBaseUrl: string,
  bffToken: string,
  tenantSlug: string,
  subject: string
): Promise<DigikeyTokenExchange | null> {
  const base = digikeyBaseUrl.replace(/\/$/, "");
  // digikey runs in a sleep-on-idle container: the first call after idle can
  // 5xx / time out for ~50s while it boots. Retry transient failures with
  // backoff inside a 100s overall budget instead of surfacing "assistant not
  // available". The budget bounds the whole loop, not each attempt: without it
  // 7 attempts x 30s plus 56s of backoff held the visitor's first request for
  // ~266s, more than twice the ~100s this comment used to claim.
  //
  // The budget bounds the exchange up to the response headers, not the body:
  // the per-attempt abort timer is released when the headers arrive, so a
  // response that then stalls its body is not bounded by it.
  const ATTEMPT_TIMEOUT_MS = DIGIKEY_BFF_ATTEMPT_TIMEOUT_MS;
  const BUDGET_MS = DIGIKEY_BFF_RETRY_BUDGET_MS;
  const delays = DIGIKEY_BFF_RETRY_DELAYS_MS;
  const startedAt = Date.now();
  for (let i = 0; i < delays.length; i++) {
    const beforeWait = BUDGET_MS - (Date.now() - startedAt);
    if (beforeWait <= 0) break;
    if (delays[i]) {
      await new Promise((r) => setTimeout(r, Math.min(delays[i], beforeWait)));
    }
    const attemptBudget = Math.min(ATTEMPT_TIMEOUT_MS, BUDGET_MS - (Date.now() - startedAt));
    if (attemptBudget <= 0) break;
    let res: Response | null = null;
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), attemptBudget);
    try {
      res = await fetch(`${base}/v1/oauth/token`, {
        method: "POST",
        signal: ctrl.signal,
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
    } catch {
      continue; // network error / timeout while waking
    } finally {
      clearTimeout(t);
    }
    if (!res) continue;
    if (res.ok) {
      const data = (await res.json()) as TokenJson;
      return parseTokenPayload(data);
    }
    const transient = res.status >= 500 || res.status === 429 || res.status === 408;
    if (!transient) return null;
  }
  return null;
}

export function isDigikeyApiKeyMaterial(token: string): boolean {
  return token.startsWith(DIGIKEY_PREFIX);
}

export { DIGIKEY_PREFIX };
