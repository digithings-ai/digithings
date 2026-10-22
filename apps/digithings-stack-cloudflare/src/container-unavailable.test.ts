/**
 * DIG-4928: a container hop that rejects with a value that is not an Error
 * must not escape as an uncaught exception.
 *
 * The production failure (digithings-stack, 2026-10-21 13:02Z): the hop to
 * the container rejected with a Date instance, not an Error. The
 * @cloudflare/containers package rethrows such a value verbatim from its
 * proxy catch, so it left the Durable Object as an uncaught exception and the
 * platform recorded it with `String(value)`: the whole error text of the row
 * was a bare date, and the client got a failure it cannot act on.
 *
 * The value carries no message, no stack and no type, so it cannot be
 * classified as an eviction or as a failed container. It is answered with the
 * retryable 503 `container_unavailable` instead, and it is NOT replayed: a
 * value that came out of the hop says nothing about whether the request
 * reached the container, so a second attempt could submit it twice.
 *
 * Behavioural pins on the pure helpers live here; the wiring in index.ts is
 * pinned by source text in container-unavailable-wiring.test.js (index.ts
 * imports `cloudflare:workers` / `@cloudflare/containers` and cannot run under
 * vitest — the same split container-retry-wiring.test.js uses).
 */
import { describe, expect, it } from "vitest";
import {
  CONTAINER_UNAVAILABLE_CODE,
  containerFailedResponse,
  containerUnavailableResponse,
  describeValue,
  isContainerEvictedError,
  isContainerFailedError,
  isNonErrorRejection,
  safeErrorMessage,
} from "./container-errors";
import { fetchWithContainerRetry, isContainerRecycledResponse } from "./container-retry";

/** The exact value the production hop rejected with (a Date, not an Error). */
const OPAQUE_REJECTION = new Date("2026-10-21T12:56:13Z");

describe("isNonErrorRejection", () => {
  it("is true for a Date and for a plain object", () => {
    expect(isNonErrorRejection(OPAQUE_REJECTION)).toBe(true);
    expect(isNonErrorRejection({ code: "whatever" })).toBe(true);
    expect(isNonErrorRejection(42)).toBe(true);
  });

  it("is false for a real Error and for its subclasses", () => {
    class Boom extends Error {}
    expect(isNonErrorRejection(new Error("boom"))).toBe(false);
    expect(isNonErrorRejection(new Boom("boom"))).toBe(false);
  });

  it("is true for a value that cannot be inspected", () => {
    // `instanceof` walks the prototype chain and a revoked proxy throws
    // there. A guard that throws would turn a caught failure back into an
    // uncaught one, which is the failure this guard exists to stop.
    const revoked = Proxy.revocable({}, {});
    revoked.revoke();
    expect(isNonErrorRejection(revoked.proxy)).toBe(true);
  });
});

describe("describeValue", () => {
  it("describes a Date as it stands", () => {
    // The platform renders such a value the same way, so the log keeps the
    // bare date — but the log also says what it was, which the platform row
    // never did. The rendering is the runtime's own (the timezone is the
    // runtime's), so the pin is not a fixed string.
    expect(describeValue(OPAQUE_REJECTION)).toBe(String(OPAQUE_REJECTION));
    expect(describeValue(OPAQUE_REJECTION)).toMatch(/Oct 21 2026/);
  });

  it("falls back when the value cannot be rendered", () => {
    const hostile = {
      toString() {
        throw new Error("no");
      },
    };
    expect(describeValue(hostile)).not.toBe("");
    const revoked = Proxy.revocable({}, {});
    revoked.revoke();
    expect(describeValue(revoked.proxy)).not.toBe("");
  });

  it("keeps the query string of a URL out of the description", () => {
    // The value of a rejected hop can be the request line of the request that
    // failed, and a token of that request rides in the query string (run-watch
    // DIG-4928, 2026-10-21: 16 error rows on digithings-digichat whose message
    // was the raw value). The description goes into the log and into the
    // answer, so the token must not be in it.
    const described = describeValue(
      "GET https://digithings.ai/embed?host=occ.digithings.ai&token=s3cret",
    );
    expect(described).not.toContain("s3cret");
    expect(described).not.toContain("token=");
    // The path stays, so the operator still reads which request failed.
    expect(described).toContain("https://digithings.ai/embed");
  });

  it("keeps the query string of a URL out of the message", () => {
    const message = safeErrorMessage(
      "failed to GET https://digithings.ai/embed?token=s3cret",
    );
    expect(message).not.toContain("s3cret");
    expect(message).toContain("https://digithings.ai/embed");
  });
});

describe("containerUnavailableResponse", () => {
  it("answers a retryable 503 with the machine-readable code", async () => {
    const response = containerUnavailableResponse("stack", "the hop failed");
    expect(response.status).toBe(503);
    expect(response.headers.get("Retry-After")).toBe("5");
    const body = (await response.json()) as { code?: string; message?: string };
    expect(body.code).toBe(CONTAINER_UNAVAILABLE_CODE);
    expect(body.message).toContain("the hop failed");
  });
});

describe("the retry helper answers an opaque rejection", () => {
  it("answers 503 container_unavailable when the hop rejects with a Date", async () => {
    let attempts = 0;
    const response = await fetchWithContainerRetry(async () => {
      attempts += 1;
      throw OPAQUE_REJECTION;
    });
    // One attempt only: the request is not replayed.
    expect(attempts).toBe(1);
    expect(response.status).toBe(503);
    expect(response.headers.get("Retry-After")).toBe("5");
    const body = (await response.json()) as { code?: string };
    expect(body.code).toBe(CONTAINER_UNAVAILABLE_CODE);
  });

  it("answers the same way for a plain object", async () => {
    const response = await fetchWithContainerRetry(async () => {
      throw { code: "whatever" };
    });
    expect(response.status).toBe(503);
    const body = (await response.json()) as { code?: string };
    expect(body.code).toBe(CONTAINER_UNAVAILABLE_CODE);
  });

  it("still rethrows a real Error", async () => {
    // A real error carries a message, a stack and a type: the caller has to
    // see it, so it is not swallowed by the guard.
    await expect(
      fetchWithContainerRetry(async () => {
        throw new Error("boom");
      }),
    ).rejects.toThrow("boom");
  });

  it("still retries a recycled container once", async () => {
    let attempts = 0;
    const response = await fetchWithContainerRetry(async () => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error(
          "Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.",
        );
      }
      return new Response("served", { status: 200 });
    });
    expect(attempts).toBe(2);
    expect(response.status).toBe(200);
  });
});

describe("the machine-readable code is pinned", () => {
  it("is the literal container_unavailable", () => {
    // Not the constant compared with itself: the literal is what the client
    // and the digichat BFF read, so a change of the string is a change of the
    // contract and has to be a deliberate one.
    expect(CONTAINER_UNAVAILABLE_CODE).toBe("container_unavailable");
  });

  it("is what the answer carries on the wire", async () => {
    const response = containerUnavailableResponse("stack", "the hop failed");
    const body = (await response.json()) as { code?: string };
    expect(body.code).toBe("container_unavailable");
  });
});

describe("an unavailable answer is never a recycle signal", () => {
  it("is not classified as a recycled response", async () => {
    // A hop that rejected with a value that is not an Error is answered with
    // `container_unavailable`, and that answer must never be replayed: a
    // value that came out of the hop says nothing about whether the request
    // reached the container, so a second attempt could submit it twice.
    const response = containerUnavailableResponse("stack", "the hop failed");
    expect(await isContainerRecycledResponse(response)).toBe(false);
  });

  it("makes the retry helper send the request exactly once", async () => {
    let attempts = 0;
    const response = await fetchWithContainerRetry(async () => {
      attempts += 1;
      return containerUnavailableResponse("stack", "the hop failed");
    });
    expect(attempts).toBe(1);
    expect(response.status).toBe(503);
    const body = (await response.json()) as { code?: string };
    expect(body.code).toBe("container_unavailable");
  });

  it("still replays a recycled container exactly once", async () => {
    // The counterpart of the pin above: the retry-once behaviour of a
    // recycled container stays, so the new code does not silence it.
    let attempts = 0;
    const response = await fetchWithContainerRetry(async () => {
      attempts += 1;
      if (attempts === 1) {
        return containerFailedResponse("stack", "the container exited");
      }
      return new Response("served", { status: 200 });
    });
    expect(attempts).toBe(2);
    expect(response.status).toBe(200);
  });
});

describe("the answer names the service it came from", () => {
  it("says mcp for the reserved mcp container", async () => {
    const response = await fetchWithContainerRetry(async () => {
      throw OPAQUE_REJECTION;
    }, { service: "mcp" });
    const body = (await response.json()) as { message?: string };
    expect(body.message).toContain("mcp container unavailable");
  });

  it("says stack by default", async () => {
    const response = await fetchWithContainerRetry(async () => {
      throw OPAQUE_REJECTION;
    });
    const body = (await response.json()) as { message?: string };
    expect(body.message).toContain("stack container unavailable");
  });
});

describe("safeErrorMessage", () => {
  it("gives an Error its own message and a string itself", () => {
    expect(safeErrorMessage(new Error("boom"))).toBe("boom");
    expect(safeErrorMessage("boom")).toBe("boom");
  });

  it("describes a value that cannot be rendered without throwing", () => {
    const hostile = {
      toString() {
        throw new Error("no");
      },
    };
    expect(safeErrorMessage(hostile)).not.toBe("");
    const revoked = Proxy.revocable({}, {});
    revoked.revoke();
    expect(safeErrorMessage(revoked.proxy)).not.toBe("");
  });

  it("keeps the eviction and failed classifiers from throwing", () => {
    // A classifier that throws inside a catch turns a caught failure back into
    // an uncaught one, which is the failure this guard exists to stop.
    const hostile = {
      toString() {
        throw new Error("no");
      },
    };
    expect(isContainerEvictedError(hostile)).toBe(false);
    expect(isContainerFailedError(hostile)).toBe(false);
    const revoked = Proxy.revocable({}, {});
    revoked.revoke();
    expect(isContainerEvictedError(revoked.proxy)).toBe(false);
    expect(isContainerFailedError(revoked.proxy)).toBe(false);
  });
});
