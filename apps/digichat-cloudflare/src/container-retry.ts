/**
 * Bounded retry for the digichat container proxy (DIG-4487).
 *
 * Why this exists. The digichat container id is derived from the deploying
 * commit (see paths.ts), so every deploy addresses a NEW id while the
 * previous id's instance is still running: warm, or draining for up to 15
 * minutes after the rollout's SIGTERM. `max_instances` is the number of
 * RUNNING container instances the Worker may hold, so with a single slot the
 * new instance cannot start until the old one has fully exited, and every
 * request that needs a container start fails.
 *
 * The @cloudflare/containers package surfaces that condition in two shapes,
 * depending on which error the platform produced:
 *   - 503 "There is no Container instance available at this time..." — the
 *     package's own no-instance path (its NO_CONTAINER_INSTANCE_ERROR).
 *   - 500 "Failed to start container: Maximum number of running container
 *     instances exceeded" — the platform's instance-limit error, which the
 *     package does NOT recognise as its no-instance error, so it falls
 *     through to its generic start failure.
 * Both are the same condition, so both are recognised here.
 *
 * A deploy also kills the container UNDER a request: the platform resets the
 * Durable Object and signals the instance to exit, so the in-flight request
 * fails. The package surfaces that as a 500 in two shapes:
 *   - "Error proxying request to container: <cause>" — its proxy catch.
 *   - "Container suddenly disconnected, try again" — its own answer when the
 *     connection was lost rather than the instance being replaced.
 * That is a second condition (the container died, rather than the slot being
 * busy), so it is recognised separately, but it is handled the same way: the
 * request is retried when it can be replayed, and otherwise the client is
 * told to come back.
 *
 * What this module does:
 *   1. recognises the condition,
 *   2. waits briefly and retries, but ONLY for a request whose body can be
 *      replayed safely (a request with no body). A body is never replayed.
 *   3. and if the condition is still there, returns the failure as a retryable
 *      503 with a `Retry-After` header, so the client backs off instead of
 *      hammering the Worker.
 *
 * The 503 is deliberate: the Worker is not broken, the container behind it
 * could not serve the request right now. A client that honours Retry-After
 * survives the rollout window.
 */

/** Status the package returns for its own no-instance path. */
export const NO_INSTANCE_STATUS = 503;

/** Marker in the package's 503 body ("There is no Container instance available"). */
export const NO_INSTANCE_BODY_MARKER = "no container instance available";

/**
 * Marker in the platform's instance-limit error, which the package surfaces
 * as a 500 ("Failed to start container: Maximum number of running container
 * instances exceeded").
 */
export const INSTANCE_LIMIT_BODY_MARKER = "maximum number of running container instances exceeded";

/**
 * Marker for the package's proxy catch, which it uses when the container
 * died under the request ("Error proxying request to container: <cause>").
 */
export const CONTAINER_DEATH_BODY_MARKER = "error proxying request to container:";

/**
 * Marker for the package's own answer when the connection to the container
 * was lost mid-request ("Container suddenly disconnected, try again").
 */
export const CONTAINER_DISCONNECTED_BODY_MARKER = "container suddenly disconnected";

/** Seconds the client should wait before repeating the request. */
export const RETRY_AFTER_SECONDS = 5;

/** Total attempts, the first one included. */
export const DEFAULT_ATTEMPTS = 2;

/** Pause between two attempts. */
export const DEFAULT_DELAY_MS = 1000;

export interface ContainerFetchOptions {
  /** Total attempts, the first one included. */
  attempts?: number;
  /** Pause between two attempts, in milliseconds. */
  delayMs?: number;
  /** Injected so a test never waits. */
  sleep?: (ms: number) => Promise<void>;
}

/**
 * True only for the container instance limit. A 503 raised by the application
 * inside the container (digichat answers `503 container_booting` while it is
 * cold) is NOT the instance limit and must pass through untouched.
 */
export function isInstanceLimitResponse(status: number, body: string): boolean {
  const text = body.toLowerCase();
  if (status === NO_INSTANCE_STATUS) return text.includes(NO_INSTANCE_BODY_MARKER);
  if (status === 500) return text.includes(INSTANCE_LIMIT_BODY_MARKER);
  return false;
}

/**
 * True only for a container that died under the request, which is what a
 * deploy does to the instance the Worker is talking to.
 *
 * The package surfaces that as a 500 in exactly two shapes: its proxy catch
 * ("Error proxying request to container: <cause>") and its own answer when
 * the connection was lost ("Container suddenly disconnected, try again").
 * Both are recognised by the body they start with, so a 500 raised by the
 * application inside the container — which carries neither marker — passes
 * through untouched.
 */
export function isContainerDeathResponse(status: number, body: string): boolean {
  if (status !== 500) return false;
  const text = body.toLowerCase();
  return (
    text.startsWith(CONTAINER_DEATH_BODY_MARKER) ||
    text.startsWith(CONTAINER_DISCONNECTED_BODY_MARKER)
  );
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** The original headers plus Retry-After, so the client knows to come back. */
function headersWithRetryAfter(headers: Headers): Headers {
  const next = new Headers(headers);
  next.set("Retry-After", String(RETRY_AFTER_SECONDS));
  return next;
}

/**
 * The body a client receives when the container could not be reached at all.
 * The platform aborts the Durable Object and throws when the instance just
 * restarted, so there is no response body to carry.
 *
 * The cause is deliberately NOT in this body: a platform error can carry a
 * stack trace, and internal detail must not leave the Worker. It is logged
 * instead, where the operator reads it.
 */
export const CONTAINER_UNAVAILABLE_BODY = JSON.stringify({
  error: "container_unavailable",
});

/**
 * The cause, for the Worker log only. Never returned to the client.
 */
function causeDetail(cause: unknown): string {
  const message = cause instanceof Error ? cause.message : String(cause);
  const inner = (cause as { cause?: unknown })?.cause;
  const detail = inner instanceof Error ? inner.message : "";
  return detail ? `${message}: ${detail}` : message;
}

/**
 * Calls the container once per attempt and turns a container that could not
 * serve the request right now — a busy instance slot, or an instance that
 * died under the request — into a retryable 503. `fetchOnce` is the container
 * proxy call (the single `container.fetch(request)` call site in index.ts).
 */
export async function fetchContainerWithRetry(
  request: Request,
  fetchOnce: (request: Request) => Promise<Response>,
  options: ContainerFetchOptions = {},
): Promise<Response> {
  const attempts = Math.max(1, options.attempts ?? DEFAULT_ATTEMPTS);
  const delayMs = options.delayMs ?? DEFAULT_DELAY_MS;
  const sleep = options.sleep ?? defaultSleep;
  // The first attempt consumes the request body, so only a bodyless request
  // can be replayed. A request that carries a body gets the retryable
  // failure at once rather than a body that was already sent.
  const replayable = request.body === null;
  for (let attempt = 1; ; attempt += 1) {
    let res: Response;
    try {
      res = await fetchOnce(request);
    } catch (cause) {
      // The container could not be reached at all. When the instance just
      // restarted the platform aborts the Durable Object and throws
      // ("Network connection lost."), so the request would end with NO
      // answer. A retryable answer beats a dead connection. The request is
      // not replayed: the Durable Object was aborted, so a second attempt
      // in this request would fail the same way. The client is told to come
      // back instead.
      //
      // The cause goes to the Worker log and never into the response: a
      // platform error can carry a stack trace, and internal detail must
      // not leave the Worker.
      console.error("digichat: container could not be reached", causeDetail(cause));
      return new Response(CONTAINER_UNAVAILABLE_BODY, {
        status: NO_INSTANCE_STATUS,
        headers: headersWithRetryAfter(new Headers()),
      });
    }
    if (res.status !== NO_INSTANCE_STATUS && res.status !== 500) return res;
    // Read a copy: the original response is handed back untouched when the
    // failure is neither the instance limit nor a container that died.
    const body = await res.clone().text();
    const transient =
      isInstanceLimitResponse(res.status, body) || isContainerDeathResponse(res.status, body);
    if (!transient) return res;
    if (attempt >= attempts || !replayable) {
      // The body stays in the answer, so the client can log why it was told
      // to wait, and the status becomes the retryable one.
      return new Response(body, {
        status: NO_INSTANCE_STATUS,
        statusText: res.statusText,
        headers: headersWithRetryAfter(res.headers),
      });
    }
    await sleep(delayMs);
  }
}
