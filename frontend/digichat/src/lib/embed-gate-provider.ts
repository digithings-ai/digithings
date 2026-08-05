/** How long to wait on the quota service before giving up and failing open. */
const CONSUME_TIMEOUT_MS = 2500;

/**
 * Spend one message against a tenant's quota service.
 *
 * Fails **open**: only an explicit 401/402 denies. Timeouts, 5xx and transport errors let the
 * message through, matching the existing gate's philosophy — the asset is free chat messages, and
 * an outage must not break chat on every embedding site. The accepted consequence is that the cap
 * is bypassable by anyone able to break the quota service.
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
    if (res.status === 401 || res.status === 402) return "deny";
    return "allow";
  } catch {
    return "allow";
  }
}
