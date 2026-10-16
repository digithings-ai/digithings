/** How long to wait on the quota service before giving up and failing open. */
const CONSUME_TIMEOUT_MS = 2500;

/**
 * Spend one message against a tenant's quota service.
 *
 * Fails **open** on provider outages: timeouts, 5xx and transport errors let the message through,
 * matching the existing gate's philosophy. Client errors fail closed because they indicate an
 * invalid, forbidden, or spent token rather than an unavailable quota service.
 */
export async function consumeChatAccess(
  consumeUrl: string,
  token: string,
): Promise<"allow" | "deny"> {
  try {
    const res = await fetch(consumeUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token }),
      signal: AbortSignal.timeout(CONSUME_TIMEOUT_MS),
    });
    if (res.status >= 400 && res.status < 500) return "deny";
    return "allow";
  } catch {
    return "allow";
  }
}
