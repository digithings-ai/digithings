import { describe, expect, it, vi } from "vitest";
import {
  CONTAINER_UNAVAILABLE_BODY,
  DEFAULT_ATTEMPTS,
  RETRY_AFTER_SECONDS,
  causeDetail,
  describeValue,
  fetchContainerWithRetry,
  isContainerDeathResponse,
  isInstanceLimitResponse,
} from "./container-retry";

/**
 * The package's own 503 body, verbatim (@cloudflare/containers 0.3.7,
 * dist/lib/container.js). The wording is the contract this module detects.
 */
const PACKAGE_503 =
  "There is no Container instance available at this time.\n" +
  "This is likely because you have reached your max concurrent instance count " +
  "(set in wrangler config) or are you currently provisioning the Container.\n" +
  "If you are deploying your Container for the first time, check your dashboard " +
  "to see provisioning status, this may take a few minutes.";

/**
 * The platform's instance-limit error, as the package surfaces it when the
 * platform error is not its own no-instance error: a 500 whose body is
 * "Failed to start container: " plus the platform message.
 */
const PACKAGE_500 = "Failed to start container: Maximum number of running container instances exceeded";

/**
 * The production body, verbatim. The platform's own instance-limit message
 * carries a tail ("Try again later, or try configuring a higher value for
 * max_instances") that the package keeps when it wraps the start failure
 * ("Failed to start container: " + the platform message). This is the text a
 * client actually receives when a rollout holds the slot.
 *
 * The production rows also show "Container error: Error: <the platform
 * message>". That is the package's own `console.error` in onError
 * (dist/lib/container.js), so it is a log line and never a response body:
 * the body the client sees is the wrapped one below.
 */
const PLATFORM_INSTANCE_LIMIT_500 =
  "Failed to start container: Maximum number of running container instances exceeded. " +
  "Try again later, or try configuring a higher value for max_instances";

/**
 * The package's proxy catch, verbatim (@cloudflare/containers 0.3.7,
 * dist/lib/container.js): the container died under the request.
 */
const PROXY_DEATH_500 =
  "Error proxying request to container: Connection closed: this Durable Object instance is no longer active.";

/**
 * The package's own answer when the connection to the container was lost
 * mid-request (same file, same catch).
 */
const DISCONNECTED_500 = "Container suddenly disconnected, try again";

const URL_ = "https://digithings.ai/api/health";

function noInstance503(): Response {
  return new Response(PACKAGE_503, { status: 503 });
}

function instanceLimit500(): Response {
  return new Response(PACKAGE_500, { status: 500 });
}

function proxyDeath500(): Response {
  return new Response(PROXY_DEATH_500, { status: 500 });
}

function disconnected500(): Response {
  return new Response(DISCONNECTED_500, { status: 500 });
}

/** A sleep stub that records the requested delay and never waits. */
function sleepStub() {
  return vi.fn(async (_ms: number) => {});
}

describe("isInstanceLimitResponse", () => {
  it("recognises the package's no-instance 503", () => {
    expect(isInstanceLimitResponse(503, PACKAGE_503)).toBe(true);
  });

  it("recognises the platform's instance-limit error surfaced as a 500", () => {
    expect(isInstanceLimitResponse(500, PACKAGE_500)).toBe(true);
  });

  it("recognises the production body, with the platform's own tail", () => {
    // The tail the platform adds must not stop the marker from matching.
    expect(isInstanceLimitResponse(500, PLATFORM_INSTANCE_LIMIT_500)).toBe(true);
  });

  it("does NOT recognise a 503 raised by the application inside the container", () => {
    // digichat answers 503 container_booting while it is cold. That is the
    // container being started, not the slot being busy.
    expect(isInstanceLimitResponse(503, "container_booting")).toBe(false);
  });

  it("does NOT recognise an unrelated failure", () => {
    expect(isInstanceLimitResponse(500, "boom")).toBe(false);
    expect(isInstanceLimitResponse(200, PACKAGE_503)).toBe(false);
    expect(isInstanceLimitResponse(503, "")).toBe(false);
  });
});

describe("isContainerDeathResponse", () => {
  it("recognises the package's proxy-catch body", () => {
    expect(isContainerDeathResponse(500, PROXY_DEATH_500)).toBe(true);
  });

  it("recognises the package's disconnected body", () => {
    expect(isContainerDeathResponse(500, DISCONNECTED_500)).toBe(true);
  });

  it("does NOT recognise a 500 raised by the application inside the container", () => {
    // The application answers with its own body, which carries neither
    // marker, so a real application error is not turned into a retry.
    expect(isContainerDeathResponse(500, "boom")).toBe(false);
    expect(isContainerDeathResponse(500, JSON.stringify({ error: "boom" }))).toBe(false);
  });

  it("does NOT recognise a death marker on a status other than 500", () => {
    // The package only ever surfaces a container death as a 500, so the
    // status is part of the contract.
    expect(isContainerDeathResponse(503, PROXY_DEATH_500)).toBe(false);
    expect(isContainerDeathResponse(200, DISCONNECTED_500)).toBe(false);
  });
});

describe("fetchContainerWithRetry", () => {
  it("returns a healthy response untouched and calls the container once", async () => {
    const fetchOnce = vi.fn(async () => new Response("ok", { status: 200 }));
    const sleep = sleepStub();
    const res = await fetchContainerWithRetry(new Request(URL_), fetchOnce, { sleep });
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
    expect(fetchOnce).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
  });

  it("passes an application 503 from inside the container through untouched", async () => {
    const fetchOnce = vi.fn(async () => new Response("container_booting", { status: 503 }));
    const sleep = sleepStub();
    const res = await fetchContainerWithRetry(new Request(URL_), fetchOnce, { sleep });
    expect(res.status).toBe(503);
    expect(await res.text()).toBe("container_booting");
    // Not the instance limit: no retry, and no Retry-After invented for it.
    expect(fetchOnce).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
    expect(res.headers.get("Retry-After")).toBeNull();
  });

  it("retries a bodyless request once and returns the recovered response", async () => {
    const fetchOnce = vi
      .fn<() => Promise<Response>>()
      .mockResolvedValueOnce(noInstance503())
      .mockResolvedValueOnce(new Response("ok", { status: 200 }));
    const sleep = sleepStub();
    const res = await fetchContainerWithRetry(new Request(URL_), fetchOnce, { sleep });
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
    expect(fetchOnce).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledTimes(1);
  });

  it("returns a retryable 503 with Retry-After when the slot stays busy", async () => {
    const fetchOnce = vi.fn(async () => noInstance503());
    const sleep = sleepStub();
    const res = await fetchContainerWithRetry(new Request(URL_), fetchOnce, { sleep });
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    // The cause stays in the body, so the client can log why it was told to wait.
    expect(await res.text()).toBe(PACKAGE_503);
    expect(fetchOnce).toHaveBeenCalledTimes(DEFAULT_ATTEMPTS);
    expect(sleep).toHaveBeenCalledTimes(DEFAULT_ATTEMPTS - 1);
  });

  it("turns the platform's 500 instance-limit error into the same retryable 503", async () => {
    const fetchOnce = vi.fn(async () => instanceLimit500());
    const sleep = sleepStub();
    const res = await fetchContainerWithRetry(new Request(URL_), fetchOnce, { sleep });
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    expect(await res.text()).toBe(PACKAGE_500);
    expect(fetchOnce).toHaveBeenCalledTimes(DEFAULT_ATTEMPTS);
  });

  it("never replays a request that carries a body", async () => {
    const fetchOnce = vi.fn(async () => noInstance503());
    const sleep = sleepStub();
    const request = new Request(URL_, { method: "POST", body: "hello" });
    const res = await fetchContainerWithRetry(request, fetchOnce, { sleep });
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    // The body was already sent once; it is not sent again.
    expect(fetchOnce).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
  });

  it("retries a bodyless request once when the container died under it", async () => {
    const fetchOnce = vi
      .fn<() => Promise<Response>>()
      .mockResolvedValueOnce(proxyDeath500())
      .mockResolvedValueOnce(new Response("ok", { status: 200 }));
    const sleep = sleepStub();
    const res = await fetchContainerWithRetry(new Request(URL_), fetchOnce, { sleep });
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
    expect(fetchOnce).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledTimes(1);
  });

  it("retries a bodyless request once when the connection was lost", async () => {
    const fetchOnce = vi
      .fn<() => Promise<Response>>()
      .mockResolvedValueOnce(disconnected500())
      .mockResolvedValueOnce(new Response("ok", { status: 200 }));
    const sleep = sleepStub();
    const res = await fetchContainerWithRetry(new Request(URL_), fetchOnce, { sleep });
    expect(res.status).toBe(200);
    expect(fetchOnce).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledTimes(1);
  });

  it("never replays a request that carries a body when the container died", async () => {
    const fetchOnce = vi.fn(async () => proxyDeath500());
    const sleep = sleepStub();
    const request = new Request(URL_, { method: "POST", body: "hello" });
    const res = await fetchContainerWithRetry(request, fetchOnce, { sleep });
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    // The cause stays in the body, so the client can log it.
    expect(await res.text()).toBe(PROXY_DEATH_500);
    expect(fetchOnce).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
  });

  it("returns a retryable 503 when the container keeps dying", async () => {
    const fetchOnce = vi.fn(async () => proxyDeath500());
    const sleep = sleepStub();
    const res = await fetchContainerWithRetry(new Request(URL_), fetchOnce, { sleep });
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    expect(await res.text()).toBe(PROXY_DEATH_500);
    expect(fetchOnce).toHaveBeenCalledTimes(DEFAULT_ATTEMPTS);
    expect(sleep).toHaveBeenCalledTimes(DEFAULT_ATTEMPTS - 1);
  });

  it("honours an explicit attempt budget", async () => {
    const fetchOnce = vi.fn(async () => noInstance503());
    const sleep = sleepStub();
    await fetchContainerWithRetry(new Request(URL_), fetchOnce, { attempts: 3, sleep });
    expect(fetchOnce).toHaveBeenCalledTimes(3);
    expect(sleep).toHaveBeenCalledTimes(2);
  });

  it("makes exactly one attempt when the budget is one", async () => {
    const fetchOnce = vi.fn(async () => noInstance503());
    const sleep = sleepStub();
    const res = await fetchContainerWithRetry(new Request(URL_), fetchOnce, { attempts: 1, sleep });
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    expect(fetchOnce).toHaveBeenCalledTimes(1);
    expect(sleep).not.toHaveBeenCalled();
  });
});

describe("a container that cannot be reached at all", () => {
  it("turns a rejected container fetch into a retryable 503 without leaking the cause", async () => {
    // The platform aborts the Durable Object and throws when the instance
    // just restarted (@cloudflare/containers 0.3.7: "Network connection
    // lost."), so without this the request ends with no answer at all.
    const inner = new Error("Network connection lost.");
    const failure = new Error("There is no Container instance available at this time");
    (failure as Error & { cause?: unknown }).cause = inner;
    const fetchOnce = vi.fn(async () => {
      throw failure;
    });
    const logged: string[] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      logged.push(args.map(String).join(" "));
    });
    const res = await fetchContainerWithRetry(
      new Request("https://digithings.ai/api/chat"),
      fetchOnce,
    );
    const body = await res.text();
    spy.mockRestore();

    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    // The cause is logged, not returned: a platform error can carry a
    // stack trace, and internal detail must not reach the client.
    expect(body).toBe(CONTAINER_UNAVAILABLE_BODY);
    expect(body).not.toContain("Network connection lost.");
    expect(body).not.toContain("There is no Container instance");
    // The operator still gets the cause, in the Worker log.
    expect(logged.join("\n")).toContain("Network connection lost.");
  });

  it("does not replay the request once the container is gone", async () => {
    // The Durable Object was aborted, so a second attempt in the same
    // request would fail the same way. The client is told to come back.
    const fetchOnce = vi.fn(async () => {
      throw new Error("Network connection lost.");
    });
    await fetchContainerWithRetry(new Request("https://digithings.ai/api/chat"), fetchOnce);
    expect(fetchOnce).toHaveBeenCalledTimes(1);
  });
});

describe("a cause that cannot be described", () => {
  // DIG-4928: the description of the cause runs INSIDE the catch, so a
  // description that throws turns a caught failure back into an uncaught one:
  // the helper would reject with a TypeError instead of answering the
  // retryable 503.
  it("describes a value with a hostile toString without throwing", () => {
    const hostile = {
      toString() {
        throw new Error("no");
      },
    };
    expect(causeDetail(hostile)).not.toBe("");
  });

  it("describes a revoked proxy without throwing", () => {
    const revoked = Proxy.revocable({}, {});
    revoked.revoke();
    expect(causeDetail(revoked.proxy)).not.toBe("");
  });

  it("keeps the inner cause of a real Error in the log line", () => {
    const inner = new Error("Network connection lost.");
    const failure = new Error("there is no container instance");
    (failure as Error & { cause?: unknown }).cause = inner;
    expect(causeDetail(failure)).toContain("there is no container instance");
    expect(causeDetail(failure)).toContain("Network connection lost.");
  });

  it("keeps the query string of a URL out of the description", () => {
    // The value of a rejected hop can be the request line of the request that
    // failed, and the embed token of that request rides in the query string
    // (run-watch DIG-4928, 2026-10-21: 16 error rows on digithings-digichat
    // whose message was the raw value). The description goes into the Worker
    // log, so the token must not be in it.
    const described = describeValue(
      "GET https://digithings.ai/embed?host=occ.digithings.ai&token=s3cret",
    );
    expect(described).not.toContain("s3cret");
    expect(described).not.toContain("token=");
    // The path stays, so the operator still reads which request failed.
    expect(described).toContain("https://digithings.ai/embed");
  });

  it("keeps the tail of a query string out of the description", () => {
    // The charset of a token is the operator's choice and nothing in the
    // repository pins it, so a run that stopped at a comma would leave the
    // rest of the token in the description.
    const described = describeValue("GET https://digithings.ai/embed?token=xy7,zw8");
    expect(described).not.toContain("xy7");
    expect(described).not.toContain("zw8");
    expect(described).toContain("https://digithings.ai/embed");
  });

  it("keeps the query string of a relative request target out of the description", () => {
    const described = describeValue("GET /v1/embed?token=xy7 HTTP/1.1");
    expect(described).not.toContain("xy7");
    expect(described).toContain("/v1/embed");
  });

  it("keeps the query string of a URL out of the cause detail", () => {
    const detail = causeDetail(
      new Error("failed to GET https://digithings.ai/embed?token=s3cret"),
    );
    expect(detail).not.toContain("s3cret");
    expect(detail).toContain("https://digithings.ai/embed");
  });

  it("answers the retryable 503 for a cause with a hostile toString", async () => {
    const logged: string[] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      logged.push(args.map((arg) => describeValue(arg)).join(" "));
    });
    const hostile = {
      toString() {
        throw new Error("no");
      },
    };
    const res = await fetchContainerWithRetry(
      new Request("https://digithings.ai/api/chat"),
      async () => {
        throw hostile;
      },
    );
    const body = await res.text();
    spy.mockRestore();

    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RETRY_AFTER_SECONDS));
    expect(body).toBe(CONTAINER_UNAVAILABLE_BODY);
    expect(logged.join("\n")).toContain("container could not be reached");
  });

  it("answers the retryable 503 for a revoked proxy", async () => {
    const logged: string[] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      logged.push(args.map((arg) => describeValue(arg)).join(" "));
    });
    const revoked = Proxy.revocable({}, {});
    revoked.revoke();
    const res = await fetchContainerWithRetry(
      new Request("https://digithings.ai/api/chat"),
      async () => {
        throw revoked.proxy;
      },
    );
    const body = await res.text();
    spy.mockRestore();

    expect(res.status).toBe(503);
    expect(body).toBe(CONTAINER_UNAVAILABLE_BODY);
  });
});
