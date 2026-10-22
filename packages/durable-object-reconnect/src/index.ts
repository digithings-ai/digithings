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
 * A hop can also reject with a value that is not an Error. The
 * @cloudflare/containers package rethrows such a value verbatim from its
 * proxy catch, so it leaves the Durable Object as an uncaught exception: the
 * platform renders the value as it stands, so a thrown Date leaves a bare
 * date in the log, and the value itself carries no type, no stack and no
 * message to classify. It is treated as a retryable failure of the instance
 * and the typed retryable error is raised at once, so the Worker answers
 * 503 + Retry-After instead of the value escaping (run-watch DIG-4928).
 *
 * That failure is not retried, unlike an eviction. An eviction is safe to
 * replay: the platform closed the instance before the request was delivered.
 * A value that came out of the hop says nothing about whether the request
 * reached the container, so a second attempt could submit it twice. The
 * client is told to come back instead, which is what a 503 + Retry-After
 * says.
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

/** The text used when a value cannot be read as text at all. */
const UNREADABLE_VALUE = "[unreadable value]";

/**
 * A URL inside free text.
 *
 * The scheme, the host and the path are kept; the query string and the
 * fragment are not, because that is where a secret rides (an embed token, a
 * signed link). Punctuation that ends a sentence is not part of the URL, so it
 * is not matched either.
 */
const URL_IN_TEXT = /\bhttps?:\/\/[^\s"'<>()[\],]+/g;

/**
 * The text of a description, with the query string of every URL removed.
 *
 * A hop can reject with a value that is not an Error, and one of the shapes
 * measured in production is the request line of the request that failed, with
 * the embed token in its query string (run-watch DIG-4928, 2026-10-21: 16
 * error rows on digithings-digichat whose message was the raw value). The
 * description of a value goes into the log, so the query string is removed
 * before the text is written: the log store is not the place for a token.
 *
 * Nothing else in the text changes. The operator still reads which request
 * failed, and the text of a value that carries no URL is untouched.
 */
export function stripUrlQuery(text: string): string {
  return text.replace(URL_IN_TEXT, (url) => {
    const cut = url.search(/[?#]/);
    if (cut === -1) return url;
    return `${url.slice(0, cut)}${url[cut]}[redacted]`;
  });
}

/**
 * A description of a value that is neither an Error nor a string.
 *
 * `String(value)` is what the platform itself shows when it records an
 * uncaught exception, so this is what an operator reads in the log. It can
 * throw (a hostile `toString`, a revoked proxy) and a description that throws
 * would turn a caught failure back into an uncaught one, so it falls back.
 *
 * The description never carries the query string of a URL: the value can be a
 * request line, and the log is not the place for the token it carries.
 */
function describeValue(value: unknown): string {
  try {
    return stripUrlQuery(String(value));
  } catch {
    try {
      return Object.prototype.toString.call(value);
    } catch {
      return UNREADABLE_VALUE;
    }
  }
}

/**
 * The message of a thrown value.
 *
 * A value that is not an Error and not a string gets a description instead of
 * an empty string: the platform renders such a rejection as the value itself,
 * so a thrown Date leaves a bare date in the log, and an empty string would
 * leave nothing at all (run-watch DIG-4928).
 *
 * Only an Error is read for its `message`. A plain object that happens to
 * carry a `message` property is described, not believed, so an object can
 * never talk its way into being a Durable Object eviction.
 *
 * The answer is always a string: a caller asks for text to match on, so a
 * message that is not a string is described like any other value.
 */
export function errorMessage(error: unknown): string {
  try {
    if (error instanceof Error) {
      const message = error.message;
      return typeof message === "string" ? stripUrlQuery(message) : describeValue(message);
    }
    if (typeof error === "string") return stripUrlQuery(error);
  } catch {
    // A value that cannot be inspected, or that cannot hand over its message,
    // has no message to read: it is described below instead. A guard that
    // throws would turn a caught failure back into an uncaught one.
  }
  return describeValue(error);
}

/**
 * The failure text of a thrown value, read only from a value that carries one:
 * the message of an Error, or a string that was thrown as it is.
 *
 * This is the text the eviction check reads, and it stays narrow on purpose:
 * only a value that states its own failure may be read as one. An object that
 * merely looks like a failure is described by `errorMessage` instead, so it
 * can never talk its way into being a Durable Object eviction.
 */
function failureText(error: unknown): string {
  try {
    if (error instanceof Error) {
      const message = error.message;
      return typeof message === "string" ? message : "";
    }
    if (typeof error === "string") return error;
  } catch {
    // A value that cannot be inspected states no failure.
  }
  return "";
}

/**
 * True when the failure means "the instance that should have served this
 * request is gone", so a reconnect is worth one attempt.
 *
 * Matched on the message, because the runtime raises a plain error and there is
 * no class to switch on. Every pattern requires the message to name a Durable
 * Object: the platform's own wording ("this Durable Object instance is no
 * longer active") and the sibling shapes ("Durable Object is gone", "Durable
 * Object reset"). A message that does not name one is not an eviction of the
 * instance, so it is never claimed as one: a container that says "no longer
 * active", or a Durable Object that says "storage quota exceeded", keeps its
 * own error instead of being retried and then reported as unavailable.
 */
export function isDurableObjectGone(error: unknown): boolean {
  const text = failureText(error).toLowerCase();
  if (!text) return false;
  if (!text.includes("durable object")) return false;
  return (
    text.includes("no longer active") || text.includes("is gone") || text.includes("reset")
  );
}

/**
 * True when the hop rejected with a value that is not an Error.
 *
 * Such a value carries no failure contract: no type, no stack, and a message
 * that is only `String(value)`. It cannot be classified by its text, so it is
 * not read as an eviction — but it is also not a failure the caller can act
 * on, and passing it on unchanged is exactly what let it escape as an
 * uncaught exception (run-watch DIG-4928).
 */
export function isNonErrorRejection(error: unknown): boolean {
  try {
    return !(error instanceof Error);
  } catch {
    // A value that cannot be inspected is not an Error anybody can read.
    return true;
  }
}

/**
 * Fetch through a Durable Object, reconnecting once when the instance is gone.
 *
 * `connect` resolves the stub (so the retry addresses a fresh stub) and
 * `makeRequest` builds the request for each attempt: a request that carries a
 * body can only be consumed once, so the body is re-created instead of replayed
 * from a spent stream.
 *
 * A rejection that is not an Error is not retried at all: it is reported as a
 * retryable failure of the instance straight away.
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
      if (isDurableObjectGone(error)) {
        // The instance is gone: address a fresh stub once.
        lastError = error;
        continue;
      }
      if (isNonErrorRejection(error)) {
        // The hop rejected with a value nobody can read. It is logged with its
        // description, so the failure is triageable instead of a bare value in
        // the log, and it is treated as a retryable failure of the instance:
        // the Worker answers 503 + Retry-After instead of the value escaping.
        //
        // The request is not replayed. An eviction is safe to replay because
        // the platform closed the instance before the request was delivered; a
        // value that came out of the hop says nothing about that, so a second
        // attempt could submit the same request twice.
        console.error(
          "[durable-object-reconnect] the Durable Object hop rejected with a value that is not an Error:",
          errorMessage(error),
        );
        lastError = error;
        break;
      }
      // A real error that does not name a Durable Object keeps its own error:
      // retrying it and then reporting it as an unavailable instance would
      // hide the failure the caller has to see.
      throw error;
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
