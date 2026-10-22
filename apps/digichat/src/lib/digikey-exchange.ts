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

/**
 * Per-attempt abort cap for a single digikey token request. It is a cap, not
 * a fixed window: the window an attempt actually gets is
 * `min(cap, budget left)`, so a late attempt in a mixed failure pattern can
 * get less.
 */
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
 * Why a digikey bff_session exchange failed.
 *
 * `rejected` — digikey answered and issued no token: the credential was
 * refused, or the request itself was wrong. This is a configuration problem
 * and it says so.
 *
 * `unreachable` — digikey never gave an answer we could use: every attempt
 * errored, timed out, or hit a transient status while the sleep-on-idle
 * container was waking. This is a cold dependency, and a retry fixes it.
 *
 * The two used to collapse into one `null`, so a cold digikey was reported as
 * "check DIGIKEY_BFF_TOKEN" and a real one-sided rotation looked the same
 * (DIG-4424).
 */
export type DigikeyBffSessionFailureReason = "rejected" | "unreachable";

/**
 * The outcome of one bff_session exchange: the token, or why there is none.
 */
export type DigikeyBffSessionOutcome =
  | { ok: true; exchange: DigikeyTokenExchange }
  | {
      ok: false;
      reason: DigikeyBffSessionFailureReason;
      /** The status digikey answered with, when it answered at all. */
      status: number | null;
    };

/**
 * OIDC-backed session exchange (digichat BFF → digikey). Requires DIGIKEY_BFF_TOKEN on digikey.
 */
export async function exchangeDigikeyBffSession(
  digikeyBaseUrl: string,
  bffToken: string,
  tenantSlug: string,
  subject: string
): Promise<DigikeyBffSessionOutcome> {
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
  // The last transient status digikey answered with, if any. It is kept so a
  // caller that reports "digikey never became ready" can name the status it
  // kept answering with, without exposing the body.
  let lastTransientStatus: number | null = null;
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
      // Network error / timeout while waking: the attempt produced no
      // response, so the guard below skips it and the next attempt starts.
    } finally {
      clearTimeout(t);
    }
    if (!res) continue;
    if (res.ok) {
      let data: TokenJson;
      try {
        data = (await res.json()) as TokenJson;
      } catch {
        // digikey answered, but not with a token payload. It did answer, so
        // this is a refusal of the request, not a cold dependency.
        return { ok: false, reason: "rejected", status: res.status };
      }
      const exchange = parseTokenPayload(data);
      if (exchange) return { ok: true, exchange };
      // A 200 without an access_token is digikey refusing to issue one.
      return { ok: false, reason: "rejected", status: res.status };
    }
    const transient = res.status >= 500 || res.status === 429 || res.status === 408;
    if (!transient) {
      // digikey answered and refused: 401/403 is a rejected token, 400 a
      // rejected request. Neither is fixed by waiting.
      return { ok: false, reason: "rejected", status: res.status };
    }
    lastTransientStatus = res.status;
  }
  // The loop ran out of attempts or out of budget with no usable answer:
  // digikey was cold, asleep, or down. Not a token problem.
  return { ok: false, reason: "unreachable", status: lastTransientStatus };
}

export function isDigikeyApiKeyMaterial(token: string): boolean {
  return token.startsWith(DIGIKEY_PREFIX);
}

export { DIGIKEY_PREFIX };
