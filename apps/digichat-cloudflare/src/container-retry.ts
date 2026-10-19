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
 * What this module does:
 *   1. recognises the condition,
 *   2. waits briefly and retries, but ONLY for a request whose body can be
 *      replayed safely (a request with no body). A body is never replayed.
 *   3. and if the slot is still busy, returns the failure as a retryable 503
 *      with a `Retry-After` header, so the client backs off instead of
 *      hammering the Worker.
 *
 * The 503 is deliberate: the Worker is not broken, the container slot is busy.
 * A client that honours Retry-After survives the rollout window.
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
 * Calls the container once per attempt and turns a busy instance slot into a
 * retryable 503. `fetchOnce` is the container proxy call (the single
 * `container.fetch(request)` call site in index.ts).
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
    const res = await fetchOnce(request);
    if (res.status !== NO_INSTANCE_STATUS && res.status !== 500) return res;
    // Read a copy: the original response is handed back untouched when the
    // failure is not the instance limit.
    const body = await res.clone().text();
    if (!isInstanceLimitResponse(res.status, body)) return res;
    if (attempt >= attempts || !replayable) {
      return new Response(body, {
        status: NO_INSTANCE_STATUS,
        statusText: res.statusText,
        headers: headersWithRetryAfter(res.headers),
      });
    }
    await sleep(delayMs);
  }
}
