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
 * Poll hint (seconds) for a container that is not ready. Small enough that a
 * ready container is picked up promptly, large enough that a full ~240s boot
 * costs ~50 upstream polls. The BFF clamps this into its own [1s, 30s] window.
 *
 * DIG-3226: a confirmed container eviction (see below) never uses a
 * `Retry-After` — it answers 410 `container_evicted` so callers stop retrying
 * an instance that is gone.
 */
export const CONTAINER_RETRY_AFTER_SECONDS = 5;

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

/**
 * Machine-readable code for a container that was RECYCLED or FAILED under the
 * request (DIG-4477).
 *
 * Distinct from `container_booting` on purpose. A booting container is a cold
 * start: the request is still coming, and the caller waits (`Retry-After`, plus
 * the digichat BFF's extended cold-boot budget). A container that EXITED or
 * was taken away is not coming back on its own — but a fresh instance can
 * serve the request, so the Worker retries it once (see ./container-retry.ts)
 * instead of surfacing the failure to the client.
 *
 * The digichat BFF keys its extended budget off `container_booting`, so this
 * code deliberately does NOT qualify for it: by the time the client sees
 * `container_failed` the one internal retry already failed.
 */
export const CONTAINER_FAILED_CODE = "container_failed";

/**
 * Substrings (lowercased) identifying a container that was recycled or failed
 * while the request was in flight. Sourced from the production rows of the
 * 2026-10-19 episode (DIG-4477): the rollout exit (143), the "not running"
 * refusal and the missing instance.
 *
 * Deliberately NOT matched: "Maximum number of running container instances
 * exceeded" — a capacity refusal (owned by DIG-4422), where an immediate
 * retry cannot conjure a slot. And not a port timeout: that is a cold boot.
 */
const FAILED_PATTERNS = [
  "signalled the container to exit",
  "container is not running",
  "no container instance",
] as const;

/**
 * True when the message confirms the container itself is gone or exited
 * (recycled / failed), as opposed to still booting.
 *
 * The difference matters at the call site: a failed container is worth one
 * fresh attempt, a booting container is not (it is already starting, and the
 * caller is told to wait).
 */
export function isContainerFailedError(err: unknown): boolean {
  const message =
    err instanceof Error ? err.message : typeof err === "string" ? err : String(err);
  const lowered = message.toLowerCase();
  return FAILED_PATTERNS.some((pattern) => lowered.includes(pattern));
}

/**
 * 503 for a container that was recycled or failed under the request.
 *
 * Carries `Retry-After` like the boot 503 (the client may retry), but a
 * distinct machine-readable code so the Worker can tell "still booting" from
 * "the container is gone" without parsing the message text.
 */
export function containerFailedResponse(
  service: "stack" | "mcp" | "digichat",
  message: string,
): Response {
  return Response.json(
    { code: CONTAINER_FAILED_CODE, message: `${service} container failed: ${message}` },
    {
      status: 503,
      headers: { "Retry-After": String(CONTAINER_RETRY_AFTER_SECONDS) },
    },
  );
}
