/** How long to wait on the quota service before giving up and reporting it unavailable. */
const CONSUME_TIMEOUT_MS = 2500;

/**
 * The outcome of asking a tenant's quota service to spend one message.
 *
 * - `allow`: the tenant answered and permitted the message.
 * - `deny`: the tenant answered with a client error (4xx) — an invalid, forbidden or
 *   spent token.
 * - `unavailable`: the tenant could **not** answer (5xx, timeout, transport error).
 */
export type ChatAccessVerdict = "allow" | "deny" | "unavailable";

/**
 * Spend one message against a tenant's quota service.
 *
 * Client errors fail closed: they indicate an invalid, forbidden, or spent token rather
 * than an unavailable quota service.
 *
 * An outage of the quota service is reported as `unavailable`, not as `allow`. The caller
 * still admits the message — a tenant outage must not 402 a visitor who already completed
 * the form, because verifying that form *is* the call that is down — but the entitlement
 * is then bounded server-side instead of being granted outright.
 */
export async function consumeChatAccess(
  consumeUrl: string,
  token: string,
): Promise<ChatAccessVerdict> {
  try {
    const res = await fetch(consumeUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token }),
      signal: AbortSignal.timeout(CONSUME_TIMEOUT_MS),
    });
    if (res.status >= 400 && res.status < 500) return "deny";
    if (res.status >= 500) return "unavailable";
    return "allow";
  } catch {
    return "unavailable";
  }
}
