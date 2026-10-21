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
  containerUnavailableResponse,
  describeValue,
  isNonErrorRejection,
} from "./container-errors";
import { fetchWithContainerRetry } from "./container-retry";

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
