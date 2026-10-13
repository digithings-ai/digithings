/**
 * Container eviction detection for digithings-stack-cloudflare (DIG-3226).
 *
 * Cloudflare can evict a Container / Durable Object instance (deploys,
 * placement moves, idle reaps). After an eviction the instance's in-memory
 * state is gone: retrying against it never succeeds. That must NOT reuse the
 * cold-start `container_booting` 503 (which carries `Retry-After` and tells
 * the caller to retry) — it needs a non-retryable code.
 *
 * This module is dependency-free on purpose so plain vitest can import it
 * (index.ts imports `cloudflare:workers` / `@cloudflare/containers` and
 * cannot run under vitest — see container-booting-503.test.js).
 */

/** Machine-readable code for a confirmed-evicted container. Never retryable. */
export const CONTAINER_EVSCITED_CODE = "container_evicted";

/**
 * Substrings (lowercased) identifying a confirmed Cloudflare container
 * eviction / loss in an error message. Sourced from the DIG-3226 brief title
 * (`no longer active`, `container-network-lost`) plus the generic eviction
 * vocabulary. Matched case-insensitively against the error message.
 */
const EVSCITED_PATTERNS = [
  "no longer active",
  "container-network",
  "container_network",
  "container network",
  "network lost",
  "evicted",
  "eviction",
] as const;

/**
 * True when the message confirms the container instance is gone (evicted /
 * lost), as opposed to still booting. Mirrors the digiquant-runner
 * RunLostError distinction (runner.ts `readStatus` 404 -> RunLostError):
 * only this signal means "the run is gone", everything else means
 * "the container is unreachable / still starting".
 */
export function isContainerEvictedError(
  err: unknown,
): boolean {
  const message =
    err instanceof Error ? err.message : typeof err === "string" ? err : String(err);
  const lowered = message.toLowerCase();
  return EVSCITED_PATTERNS.some((pattern) => lowered.includes(pattern));
}

/**
 * Non-retryable 410 for a confirmed-evicted container. Deliberately carries
 * NO `Retry-After` header: its absence (beside the distinct code) is what
 * keeps callers — including the digichat BFF's extended cold-boot budget,
 * which keys off `container_booting` + `Retry-After` — from retrying a
 * container that is never coming back.
 */
export function containerEvictedResponse(
  service: "stack" | "mcp" | "digichat",
  message: string,
): Response {
  return Response.json(
    { code: CONTAINER_EVSCITED_CODE, message: `${service} container evicted: ${message}` },
    { status: 410 },
  );
}
