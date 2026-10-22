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
 * A URL inside free text.
 *
 * The scheme, the host and the path are kept; the query string and the
 * fragment are not, because that is where a secret rides (an embed token, a
 * signed link).
 *
 * The run of characters that follows the scheme ends at the first whitespace
 * and at nothing else. The charset of a token is the operator's choice and
 * nothing in the repository pins it, so a run that stopped at a comma or a
 * quote would leave the tail of the token in the text. What follows the
 * query string inside that run goes with it: a period that ends the sentence
 * is part of the tail and is dropped with it.
 *
 * The scheme is matched whatever its case, because a request line that a
 * proxy wrote in upper case is still a URL.
 */
const URL_IN_TEXT = /\bhttps?:\/\/[^\s]+/gi;

/**
 * The credentials of the authority of a URL: what stands before the `@` of
 * `https://user:token@host/path`. A credential is a secret like the one in
 * a query string, so it does not stay in the text either.
 */
const AUTHORITY_CREDENTIALS = /^(https?:\/\/)[^/?#\s]*@/i;

/**
 * A relative request target inside free text, such as the request line of
 * the request that failed: `GET /v1/embed?token=... HTTP/1.1`.
 *
 * The target starts a word, so a slash that belongs to a word (as in `3/4`)
 * is not a target.
 */
const RELATIVE_TARGET_IN_TEXT = /(^|\s)(\/[^\s]*[?#][^\s]*)/g;

/**
 * The text of a description, with the query string of every URL removed.
 *
 * The value of a rejected hop can be the request line of the request that
 * failed, and a token of that request rides in the query string (run-watch
 * DIG-4928, 2026-10-21: 16 error rows on digithings-digichat whose message was
 * the raw value). The description goes into the log and into the answer, so
 * the query string is removed before the text is written: neither the log store
 * nor the client is the place for a token.
 *
 * The scheme, the host and the path stay, so the operator still reads which
 * request failed.
 */
export function stripUrlQuery(text: string): string {
  return text
    .replace(URL_IN_TEXT, (url) => {
      const withoutCredentials = url.replace(AUTHORITY_CREDENTIALS, "$1[redacted]@");
      const cut = withoutCredentials.search(/[?#]/);
      if (cut === -1) return withoutCredentials;
      return `${withoutCredentials.slice(0, cut)}${withoutCredentials[cut]}[redacted]`;
    })
    .replace(RELATIVE_TARGET_IN_TEXT, (_match, space: string, target: string) => {
      const cut = target.search(/[?#]/);
      if (cut === -1) return target;
      return `${space}${target.slice(0, cut)}${target[cut]}[redacted]`;
    });
}

/**
 * A description of a thrown value, for the log and for the answer.
 *
 * `String(value)` is what the platform shows for a value it cannot classify,
 * but it can throw (a hostile `toString`, a revoked proxy) and a description
 * that throws inside a catch would turn a caught failure back into an
 * uncaught one. So the description falls back.
 *
 * Only the description is used, never the value itself: a cause stays inside
 * the Worker, the same way the Worker log handles the cause of a container
 * that could not be reached (see ./container-retry). The description never
 * carries the query string of a URL: see `stripUrlQuery`.
 */
export function describeValue(value: unknown): string {
  try {
    return stripUrlQuery(String(value));
  } catch {
    try {
      return Object.prototype.toString.call(value);
    } catch {
      return "[unreadable value]";
    }
  }
}

/**
 * The message of a thrown value, or a description of it when it carries none.
 *
 * Total on purpose: an Error gives its own message, a string gives itself, and
 * anything else is described by `describeValue` — which cannot throw. The
 * question is asked in a way that cannot throw either: `instanceof` walks the
 * prototype chain, and a value that cannot be inspected throws there. A
 * message that throws inside a catch would turn a caught failure back into an
 * uncaught one.
 */
export function safeErrorMessage(value: unknown): string {
  try {
    if (value instanceof Error) {
      const message = value.message;
      return typeof message === "string" ? stripUrlQuery(message) : describeValue(message);
    }
    if (typeof value === "string") {
      return stripUrlQuery(value);
    }
  } catch {
    // A value that cannot be inspected is described by describeValue below.
  }
  return describeValue(value);
}

/**
 * True when a thrown value is not an Error.
 *
 * A hop can reject with a value that is not an Error: the
 * @cloudflare/containers package rethrows such a value verbatim from its
 * proxy catch, so it leaves the Durable Object as an uncaught exception and
 * the platform renders it as it stands — a thrown Date leaves nothing but a
 * bare date in the log (run-watch DIG-4928).
 *
 * Such a value carries no message, no stack and no type, so it cannot be
 * classified as an eviction or as a failed container. It is answered with the
 * retryable `container_unavailable` instead (see
 * `containerUnavailableResponse`).
 *
 * The check is asked in a way that cannot throw: `instanceof` walks the
 * prototype chain, and a value that cannot be inspected throws there. A guard
 * that throws would turn a caught failure back into an uncaught one, which is
 * the failure this guard exists to stop.
 */
export function isNonErrorRejection(value: unknown): boolean {
  try {
    return !(value instanceof Error);
  } catch {
    // A value that cannot be inspected is not an Error we can read.
    return true;
  }
}

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
  const message = safeErrorMessage(err);
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
 * while the request was in flight.
 *
 * Anchored on the PRODUCER's own vocabulary — @cloudflare/containers 0.3.7
 * (`dist/lib/container.js`) classifies a container that died under a request
 * with exactly these strings:
 *   - RUNTIME_SIGNALLED_ERROR  "runtime signalled the container to exit:"
 *     (the runtime stopped the container: a new version rollout) — this is the
 *     shape the digithings-stack Worker logged on 2026-10-19.
 *   - UNEXPECTED_EXIT_ERROR    "container exited with unexpected exit code:"
 *     (the container crashed).
 *   - NO_CONTAINER_INSTANCE_ERROR
 *     "there is no container instance that can be provided to this durable
 *     object" (the Durable Object aborted itself because the platform could
 *     not give it an instance).
 *
 * Deliberately NOT matched, and why:
 *   - "The container is not running, consider calling start()" — this Worker
 *     documents that message as the COLD-BOOT kill: the idle alarm fires
 *     mid-boot and SIGTERMs the container before its port opens, and every
 *     caller is meant to get 503 `container_booting` (see index.ts, #5762).
 *     Retrying it would retry a cold boot, which the digichat BFF's extended
 *     cold-boot budget already covers.
 *   - "the container is not listening" (NOT_LISTENING_ERROR) — the container
 *     is still starting.
 *   - "Maximum number of running container instances exceeded" — a capacity
 *     refusal (owned by DIG-4422); an immediate retry cannot conjure a slot.
 */
const FAILED_PATTERNS = [
  "signalled the container to exit",
  "container exited with unexpected exit code",
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
  const message = safeErrorMessage(err);
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

/**
 * Machine-readable code for a container hop that failed in a way nothing can
 * classify (DIG-4928).
 *
 * Distinct from `container_booting` on purpose: a booting container is a cold
 * start, the request is still coming and the caller waits. Distinct from
 * `container_failed` on purpose as well: a failed container exited under the
 * request, so a fresh instance can serve it and the Worker retries it once.
 *
 * This code is for a hop that rejected with a value that is not an Error: the
 * request is not replayed, because a value that came out of the hop says
 * nothing about whether the request reached the container, and a second
 * attempt could submit it twice. The client is told to come back, which is
 * what a 503 + `Retry-After` says.
 */
export const CONTAINER_UNAVAILABLE_CODE = "container_unavailable";

/**
 * The detail the client gets when a container hop rejected with a value that
 * is not an Error.
 *
 * The cause of the failure is deliberately NOT in the answer: a rejected
 * value can carry internal detail and a platform error can carry a stack
 * trace, and neither leaves the Worker. It is logged instead, where the
 * operator reads it. The shared package holds the same contract
 * (packages/durable-object-reconnect, `durableObjectUnavailableResponse`).
 */
export const CONTAINER_UNAVAILABLE_DETAIL =
  "the container hop rejected with a value that could not be classified";

/**
 * 503 for a container hop that rejected with a value that is not an Error.
 *
 * Carries `Retry-After` like the other 503 answers (the client may retry)
 * and a distinct machine-readable code, so the Worker can tell "the hop
 * failed in a way we cannot classify" from "the container is gone" without
 * parsing the message text — and so the retry-once wrapper does not replay
 * the request.
 *
 * The answer carries the service and the fixed detail, never the cause: the
 * cause stays in the log (see `CONTAINER_UNAVAILABLE_DETAIL`).
 */
export function containerUnavailableResponse(
  service: "stack" | "mcp" | "digichat",
): Response {
  return Response.json(
    {
      code: CONTAINER_UNAVAILABLE_CODE,
      message: `${service} container unavailable: ${CONTAINER_UNAVAILABLE_DETAIL}`,
    },
    {
      status: 503,
      headers: { "Retry-After": String(CONTAINER_RETRY_AFTER_SECONDS) },
    },
  );
}

/**
 * How a failure that came out of a container hop is classified.
 *
 * `unavailable` — the hop rejected with a value that is not an Error. The
 * value states no failure of its own, so it is neither an eviction nor a
 * failed container, and it is not replayed.
 * `evicted` — a real Error that names a confirmed eviction of the instance.
 * `failed` — a real Error that names a container that exited or was taken
 * away; a fresh instance can serve the request, so it is worth one retry.
 * `unknown` — a real Error that names neither. The caller rethrows it
 * unchanged, so an unrelated failure is never masked.
 */
export type ContainerHopFailure =
  | { kind: "unavailable"; description: string }
  | { kind: "evicted"; message: string }
  | { kind: "failed"; message: string }
  | { kind: "unknown" };

/**
 * Classify a failure that came out of a container hop, in ONE place.
 *
 * The order of the checks is the contract, and it is decided here rather
 * than at each call site so that it cannot drift between the two container
 * classes and the Worker-side retry helper:
 *
 *   1. A value that is not an Error comes FIRST. Such a value states no
 *      failure of its own, so it is never read as an eviction or as a failed
 *      container: a value that merely *renders* like one — a thrown string
 *      that names a Durable Object, for example — must not talk its way into
 *      a classification it does not carry. It is answered with the retryable
 *      `container_unavailable` and it is not replayed.
 *   2. Only a real Error is read for its message, and only then are the
 *      eviction and the failed vocabulary matched against it.
 *
 * Read the eviction first and that thrown string would be answered as an
 * eviction — a different answer for a different condition (run-watch
 * DIG-4928).
 */
export function classifyContainerHopFailure(error: unknown): ContainerHopFailure {
  if (isNonErrorRejection(error)) {
    return { kind: "unavailable", description: describeValue(error) };
  }
  const message = safeErrorMessage(error);
  if (isContainerEvictedError(message)) {
    return { kind: "evicted", message };
  }
  if (isContainerFailedError(message)) {
    return { kind: "failed", message };
  }
  return { kind: "unknown" };
}

/**
 * The message of a response that says "the container died under this
 * request", or null when it says nothing of the sort.
 *
 * @cloudflare/containers 0.3.7 catches the error ITSELF in `containerFetch`
 * and answers with a 500 instead of throwing — its own comment on the branch
 * is "This error means that the container might've just restarted". Two
 * shapes, both status 500:
 *   - "Container suddenly disconnected, try again" — the network to the
 *     container was lost.
 *   - "Error proxying request to container: <message>" — the inner message is
 *     the container's own error (the runtime signalled the exit, the
 *     container crashed, ...). It only counts when it is one of the
 *     failed-container shapes above.
 *
 * The body is read from a CLONE, so the caller keeps a readable response.
 */
export async function containerRestartMessage(
  response: Response,
): Promise<string | null> {
  if (response.status !== 500) {
    return null;
  }
  let text: string;
  try {
    text = await response.clone().text();
  } catch {
    return null;
  }
  const lowered = text.toLowerCase();
  if (lowered.includes("container suddenly disconnected")) {
    return text.trim();
  }
  const marker = "error proxying request to container:";
  const at = lowered.indexOf(marker);
  if (at === -1) {
    return null;
  }
  const inner = text.slice(at + marker.length);
  return isContainerFailedError(inner) ? inner.trim() : null;
}
