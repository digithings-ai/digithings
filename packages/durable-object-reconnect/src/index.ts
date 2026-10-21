/**
 * Reconnect for Workers that call a Durable Object that owns a container.
 *
 * Several Workers in this repo hand every request to a Durable Object that
 * owns a batch container: digiquant-runner (the digiquant desk runner),
 * twelvex-runner (the twelve-x ingest and heartbeat runner), and the next
 * Worker with a container binding. When the platform closes that Durable
 * Object instance while a request is in flight (eviction, a recycle, the
 * platform closing the instance) the runtime closes the connection and the
 * request never reaches the container. The platform's own message says what to
 * do about it:
 *
 *   Connection closed: this Durable Object instance is no longer active.
 *   Reconnect or retry the request.
 *
 * Without error handling around that hop the close escapes the fetch handler
 * and the caller gets a hard failure it cannot act on. Measured in production:
 * 10 failed requests inside five minutes on digiquant-runner (run-watch
 * DIG-4529, 2026-10-20), and 4 error rows inside two hours on twelvex-runner
 * (run-watch DIG-4753, 2026-10-20). The same platform message appeared on
 * digithings-stack in the same window: a platform-side recycle wave across the
 * Workers that hold a container Durable Object.
 *
 * This module is the shared answer, so the next Worker with a container
 * binding inherits it instead of writing its own:
 *
 *   - reconnect once, because the Durable Object id is a NAME: the next call
 *     reaches the live instance (which starts a fresh container on demand);
 *   - and when even the reconnect fails, raise a typed retryable error so the
 *     Worker can answer 503 + Retry-After instead of hammering a runner that
 *     is still coming up.
 *
 * The reconnect is deliberately one attempt: a Durable Object that has just
 * been evicted may need a moment to start, and a tight loop would turn one
 * eviction into a burst.
 *
 * It is dependency-free (no `cloudflare:workers`, no `@cloudflare/containers`)
 * so plain vitest can import it and a Worker can bundle it.
 */

/** Body code the Worker returns when the instance could not be reached. */
export const DURABLE_OBJECT_UNAVAILABLE = "durable_object_unavailable";

/** Seconds a caller should wait before retrying, sent as `Retry-After`. */
export const RECONNECT_RETRY_AFTER_SECONDS = 30;

/** The shape of a Durable Object stub, narrowed to what this module uses. */
export type DurableObjectFetcher = {
  fetch: (request: Request) => Promise<Response>;
};

/** Thrown when a reconnect was attempted and the instance is still gone. */
export class DurableObjectUnavailableError extends Error {
  /** Callers may back off and retry: the runner is not permanently broken. */
  readonly retryable = true;

  constructor(readonly lastError?: unknown) {
    super(DURABLE_OBJECT_UNAVAILABLE);
    this.name = "DurableObjectUnavailableError";
  }
}

/** The message of a thrown value, or an empty string when there is none. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message ?? "";
  if (typeof error === "string") return error;
  return "";
}

/**
 * True when the failure means "the instance that should have served this
 * request is gone", so a reconnect is worth one attempt.
 *
 * Matched on the message, because the runtime raises a plain error and there is
 * no class to switch on. The first pattern is the platform's own wording; the
 * others are the sibling shapes and require the message to name a Durable
 * Object, so unrelated failures are never mistaken for an eviction.
 */
export function isDurableObjectGone(error: unknown): boolean {
  const text = errorMessage(error).toLowerCase();
  if (!text) return false;
  if (text.includes("no longer active")) return true;
  if (!text.includes("durable object")) return false;
  return text.includes("is gone") || text.includes("reset");
}

/**
 * Fetch through a Durable Object, reconnecting once when the instance is gone.
 *
 * `connect` resolves the stub (so the retry addresses a fresh stub) and
 * `makeRequest` builds the request for each attempt: a request that carries a
 * body can only be consumed once, so the body is re-created instead of replayed
 * from a spent stream.
 */
export async function fetchDurableObject(
  connect: () => DurableObjectFetcher,
  makeRequest: () => Request,
  options: { attempts?: number } = {},
): Promise<Response> {
  const attempts = Math.max(1, options.attempts ?? 2);
  let lastError: unknown;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await connect().fetch(makeRequest());
    } catch (error) {
      if (!isDurableObjectGone(error)) throw error;
      lastError = error;
    }
  }
  throw new DurableObjectUnavailableError(lastError);
}

/**
 * The answer a Worker gives when the instance could not be reached, even after
 * the reconnect: 503 with `Retry-After`, so the caller backs off instead of
 * hammering a runner that is still coming up.
 *
 * `detail` says what happened in the Worker's own words. The cause of the
 * failure is not in the body: a platform error can carry a stack trace, and
 * internal detail must not leave the Worker.
 */
export function durableObjectUnavailableResponse(detail: string): Response {
  return Response.json(
    { error: DURABLE_OBJECT_UNAVAILABLE, detail },
    {
      status: 503,
      headers: { "Retry-After": String(RECONNECT_RETRY_AFTER_SECONDS) },
    },
  );
}
