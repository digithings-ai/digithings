import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_ATTEMPTS,
  RETRY_AFTER_SECONDS,
  fetchContainerWithRetry,
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

const URL_ = "https://digithings.ai/api/health";

function noInstance503(): Response {
  return new Response(PACKAGE_503, { status: 503 });
}

function instanceLimit500(): Response {
  return new Response(PACKAGE_500, { status: 500 });
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
