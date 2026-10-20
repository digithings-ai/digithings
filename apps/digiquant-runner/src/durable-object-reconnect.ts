/**
 * digiquant-runner hands every request to the Durable Object that owns the
 * batch container. When that instance disappears while a request is in flight
 * (eviction, a recycle, the platform closing the instance) the runtime closes
 * the connection and the request never reaches the container. The platform's
 * own message says what to do about it:
 *
 *   Connection closed: this Durable Object instance is no longer active.
 *   Reconnect or retry the request.
 *
 * The Worker had no error handling around that hop, so the close surfaced as an
 * unhandled 500 (run-watch DIG-4529: 10 failed requests inside five minutes on
 * 2026-10-20). This module reconnects once and, when even the reconnect fails,
 * raises a typed retryable error so the Worker can answer 503 + Retry-After
 * instead of hammering a runner that is still coming up.
 *
 * The reconnect is deliberately one attempt: a Durable Object that has just
 * been evicted may need a moment to start, and a tight loop would turn one
 * eviction into a burst.
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
