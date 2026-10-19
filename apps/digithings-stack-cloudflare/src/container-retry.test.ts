/**
 * DIG-4477: a recycled Container must not fail the client request.
 *
 * The production failure (digithings-stack, 2026-10-19 16:40Z-18:15Z): the
 * stack container was recycled while it served requests, so the request that
 * landed on it died. The Worker logged 11 error-level rows whose message was
 * the request URL and 5 rows `Connection closed: this Durable Object instance
 * is no longer active. Reconnect or retry the request.` in the same band, and
 * the client saw the failure instead of an answer.
 *
 * These are behavioural tests of the pure helper (./container-retry.ts has no
 * platform imports, so plain vitest can import it — the same reason
 * ./container-errors.ts is dependency-free). index.ts cannot be imported here
 * (it imports `cloudflare:workers` / `@cloudflare/containers`), so the wiring
 * is pinned by source text in container-retry-wiring.test.js.
 */
import { describe, expect, it } from "vitest";
import {
  containerEvictedResponse,
  containerFailedResponse,
} from "./container-errors";
import {
  fetchWithContainerRetry,
  isContainerRecycledError,
  isContainerRecycledResponse,
} from "./container-retry";

/** The exact message the stack Worker logged during the 2026-10-19 episode. */
const RECYCLE_ERROR =
  "Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.";

describe("isContainerRecycledError", () => {
  it("matches the Durable Object reset message from the episode", () => {
    expect(isContainerRecycledError(RECYCLE_ERROR)).toBe(true);
    expect(isContainerRecycledError(new Error(RECYCLE_ERROR))).toBe(true);
  });

  it("matches the container exit / missing-instance messages", () => {
    expect(
      isContainerRecycledError(
        "Container error: Runtime signalled the container to exit due to a new version rollout: 143",
      ),
    ).toBe(true);
    expect(
      isContainerRecycledError("The container is not running, consider calling start()"),
    ).toBe(true);
    expect(isContainerRecycledError("no container instance")).toBe(true);
  });

  it("does not match a cold boot or a capacity refusal", () => {
    // A booting container is already starting: the client's own Retry-After
    // budget is the right answer, and a retry here would double the wait.
    expect(isContainerRecycledError("port 8000 not ready after 180000ms")).toBe(false);
    // Capacity refusal: an immediate retry cannot conjure a slot (DIG-4422).
    expect(
      isContainerRecycledError("Maximum number of running container instances exceeded"),
    ).toBe(false);
    expect(isContainerRecycledError("")).toBe(false);
  });
});

describe("a recycled container does not fail the request", () => {
  it("retries once and answers the client when the instance was replaced", async () => {
    let attempts = 0;
    const response = await fetchWithContainerRetry(async () => {
      attempts += 1;
      if (attempts === 1) {
        // What the Worker saw: the Durable Object instance was replaced
        // mid-request. The Durable Object id is a NAME, so the next call
        // reaches the live instance.
        throw new Error(RECYCLE_ERROR);
      }
      return new Response("ok", { status: 200 });
    });
    expect(attempts).toBe(2);
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("ok");
  });

  it("retries once on the evicted 410 the container wrapper answers", async () => {
    let attempts = 0;
    const response = await fetchWithContainerRetry(async () => {
      attempts += 1;
      if (attempts === 1) {
        return containerEvictedResponse("stack", "instance is no longer active");
      }
      return new Response("ok", { status: 200 });
    });
    expect(attempts).toBe(2);
    expect(response.status).toBe(200);
  });

  it("retries once on the failed-container 503", async () => {
    let attempts = 0;
    const response = await fetchWithContainerRetry(async () => {
      attempts += 1;
      if (attempts === 1) {
        return containerFailedResponse("stack", "container is not running");
      }
      return new Response("ok", { status: 200 });
    });
    expect(attempts).toBe(2);
    expect(response.status).toBe(200);
  });
});

describe("the retry is bounded and never re-serves a served request", () => {
  it("does not retry a request that already succeeded", async () => {
    let attempts = 0;
    const response = await fetchWithContainerRetry(async () => {
      attempts += 1;
      return new Response("ok", { status: 200 });
    });
    expect(attempts).toBe(1);
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("ok");
  });

  it("does not retry an error that is not a recycle", async () => {
    let attempts = 0;
    await expect(
      fetchWithContainerRetry(async () => {
        attempts += 1;
        throw new Error("digigraph: upstream 500");
      }),
    ).rejects.toThrow("digigraph: upstream 500");
    expect(attempts).toBe(1);
  });

  it("gives up after one retry and surfaces the failure", async () => {
    let attempts = 0;
    await expect(
      fetchWithContainerRetry(async () => {
        attempts += 1;
        throw new Error(RECYCLE_ERROR);
      }),
    ).rejects.toThrow(RECYCLE_ERROR);
    expect(attempts).toBe(2);
  });

  it("keeps the machine-readable container answer when the retry dies hard", async () => {
    let attempts = 0;
    const response = await fetchWithContainerRetry(async () => {
      attempts += 1;
      if (attempts === 1) {
        return containerEvictedResponse("stack", "instance is no longer active");
      }
      throw new Error("digigraph: upstream 500");
    });
    expect(attempts).toBe(2);
    // The 410 is the machine-readable answer the client can act on; the raw
    // exception raised by the retry must not replace it.
    expect(response.status).toBe(410);
    const body = (await response.json()) as { code?: string };
    expect(body.code).toBe("container_evicted");
  });

  it("honours a zero-retry budget", async () => {
    let attempts = 0;
    await expect(
      fetchWithContainerRetry(
        async () => {
          attempts += 1;
          throw new Error(RECYCLE_ERROR);
        },
        { retries: 0 },
      ),
    ).rejects.toThrow(RECYCLE_ERROR);
    expect(attempts).toBe(1);
  });
});

describe("isContainerRecycledResponse", () => {
  it("matches the two container codes", async () => {
    expect(
      await isContainerRecycledResponse(containerEvictedResponse("stack", "gone")),
    ).toBe(true);
    expect(
      await isContainerRecycledResponse(containerFailedResponse("stack", "exited")),
    ).toBe(true);
  });

  it("does not match a booting 503 or an ordinary answer", async () => {
    const booting = Response.json(
      { code: "container_booting", message: "stack container not ready: booting" },
      { status: 503, headers: { "Retry-After": "5" } },
    );
    expect(await isContainerRecycledResponse(booting)).toBe(false);
    expect(await isContainerRecycledResponse(new Response("ok"))).toBe(false);
    expect(await isContainerRecycledResponse(new Response("{}", { status: 503 }))).toBe(
      false,
    );
  });

  it("leaves the body of the response it inspects readable", async () => {
    const response = containerEvictedResponse("stack", "gone");
    expect(await isContainerRecycledResponse(response)).toBe(true);
    const body = (await response.json()) as { code?: string };
    expect(body.code).toBe("container_evicted");
  });
});
