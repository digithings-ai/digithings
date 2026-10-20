/**
 * Retry-once for a recycled / failed Container (DIG-4477).
 *
 * The failure this exists for, measured in production on 2026-10-19 between
 * 16:40Z and 18:15Z: the digithings-stack Worker logged 11 error-level rows
 * whose message was the request URL (`GET https://search.digithings.ai/`) and
 * 5 rows `Connection closed: this Durable Object instance is no longer
 * active. Reconnect or retry the request.` in the same band. The stack
 * container was recycled while it served requests, so whichever request landed
 * on it died: the Durable Object instance was replaced (its in-memory state
 * gone) and the container it addressed was taken away underneath it.
 *
 * Two shapes reach the client, and both are failures the client should not
 * have to own:
 *   1. The Durable Object stub call THROWS (`... instance is no longer
 *      active`). Nothing in the Worker caught it, so the request surfaced as
 *      an uncaught error and the client got a failure it cannot act on.
 *   2. The container wrapper catches the eviction itself and answers
 *      410 `container_evicted` (DIG-3226), or 503 `container_failed` when the
 *      container exited instead of being evicted.
 *
 * A fresh attempt is what actually fixes both: the Durable Object id is a
 * NAME, so the next call reaches the live instance (which starts a fresh
 * container on demand), and a container that exited is started again by
 * `startAndWaitForPorts`. So the route retries ONCE instead of surfacing the
 * failure.
 *
 * Deliberately dependency-free (no `cloudflare:workers` /
 * `@cloudflare/containers`) so plain vitest can import it — the same reason
 * ./container-errors.ts is dependency-free. index.ts cannot be imported under
 * vitest, so the wiring is pinned by source text in
 * container-retry-wiring.test.js.
 */
import {
  CONTAINER_EVSCITED_CODE,
  CONTAINER_FAILED_CODE,
  containerRestartMessage,
  isContainerEvictedError,
  isContainerFailedError,
} from "./container-errors";

/**
 * True when the failure means "the container/instance backing this request is
 * gone or exited", i.e. a fresh attempt can serve it.
 *
 * Covers the evicted vocabulary (the instance is gone) and the failed
 * vocabulary (the container exited or was taken away). It deliberately does
 * NOT cover a cold boot (`port 8000 not ready after 180000ms`) — that
 * container is already starting and the client is told to wait — nor the
 * capacity refusal (`Maximum number of running container instances
 * exceeded`), where an immediate retry cannot conjure a slot (DIG-4422).
 */
export function isContainerRecycledError(err: unknown): boolean {
  return isContainerEvictedError(err) || isContainerFailedError(err);
}

/** Read the machine-readable `code` of a JSON error body, or null. */
async function readErrorCode(response: Response): Promise<string | null> {
  try {
    // clone(): the caller still owns the body of the response it gets back.
    const body = (await response.clone().json()) as unknown;
    if (body && typeof body === "object" && "code" in body) {
      const code = (body as { code?: unknown }).code;
      return typeof code === "string" ? code : null;
    }
    return null;
  } catch {
    // Not JSON, or no body: not a container code.
    return null;
  }
}

/**
 * True when the response is the machine-readable answer for a recycled or
 * failed container — the two codes the container wrapper answers with.
 *
 * A `container_booting` 503 is NOT one of them: that container is starting,
 * and the client's own `Retry-After` budget is the right answer for it.
 *
 * A 500 that carries the container's own restart signal counts too, because
 * @cloudflare/containers answers a container that died mid-request with a
 * 500 instead of throwing (see containerRestartMessage). The container
 * wrapper normally converts that 500 into `container_failed` first, so this
 * is the fallback for any path that does not go through the wrapper.
 */
export async function isContainerRecycledResponse(
  response: Response,
): Promise<boolean> {
  if (response.status === 410 || response.status === 503) {
    const code = await readErrorCode(response);
    return code === CONTAINER_EVSCITED_CODE || code === CONTAINER_FAILED_CODE;
  }
  if (response.status === 500) {
    return (await containerRestartMessage(response)) !== null;
  }
  return false;
}

export interface ContainerRetryOptions {
  /**
   * How many extra attempts after the first one. Default 1: exactly one
   * retry, which is the whole point — the second attempt reaches a fresh
   * instance, and a third would only bill another cold start.
   */
  retries?: number;
}

/**
 * Run `attempt`, retrying once when the container backing it was recycled.
 *
 * `attempt` is a closure, not a Request: every attempt must be able to build
 * its own request (the body of a consumed Request cannot be replayed), and
 * the caller clones per attempt.
 *
 * The contract:
 *   - a response that is neither an error nor a container code is returned
 *     untouched, after exactly ONE attempt (a served request is never
 *     re-served);
 *   - a thrown error that is not a recycle signal is re-thrown immediately —
 *     an application error inside the container must not be retried, and it
 *     must not be masked by the answer of an earlier attempt either: if the
 *     retry reached a live container and failed for an unrelated reason, the
 *     client is told "the container is gone" while the real error is dropped;
 *   - a recycled failure (thrown, 410 `container_evicted`, 503
 *     `container_failed`, or a 500 carrying the container's restart signal)
 *     is retried ONCE; if that attempt fails too, the failure surfaces
 *     exactly as it would have without this helper.
 *
 * One honest caveat: a non-idempotent request whose answer was lost to the
 * recycle can be executed twice. The alternative — surfacing the failure —
 * is what the digichat BFF's own cold-boot budget already retries from the
 * client side, so the retry moves a duplicate window that exists today
 * rather than opening a new one.
 */
export async function fetchWithContainerRetry(
  attempt: () => Promise<Response>,
  options: ContainerRetryOptions = {},
): Promise<Response> {
  const retries = Math.max(0, options.retries ?? 1);
  let attemptIndex = 0;
  for (;;) {
    try {
      const response = await attempt();
      if (attemptIndex < retries && (await isContainerRecycledResponse(response))) {
        attemptIndex += 1;
        continue;
      }
      return response;
    } catch (error) {
      if (attemptIndex >= retries || !isContainerRecycledError(error)) {
        throw error;
      }
      attemptIndex += 1;
    }
  }
}
