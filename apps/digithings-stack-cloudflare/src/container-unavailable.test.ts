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
/// <reference types="node" />
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  CONTAINER_UNAVAILABLE_CODE,
  CONTAINER_UNAVAILABLE_DETAIL,
  classifyContainerHopFailure,
  containerFailedResponse,
  containerUnavailableResponse,
  describeValue,
  isContainerEvictedError,
  isContainerFailedError,
  isNonErrorRejection,
  safeErrorMessage,
} from "./container-errors";
import { fetchWithContainerRetry, isContainerRecycledResponse } from "./container-retry";

/**
 * The root of the repository, so a test can read the other copy of the
 * redactor.
 */
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

/**
 * The code of a redactor, without the doc comment around it.
 */
function redactorCode(file: string): string {
  const source = readFileSync(file, "utf8");
  const start = source.indexOf("const URL_IN_TEXT");
  const fn = source.indexOf("export function stripUrlQuery");
  const end = source.indexOf("\n}\n", fn);
  return source
    .slice(start, end)
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      return !(
        trimmed.startsWith("*") ||
        trimmed.startsWith("/**") ||
        trimmed.startsWith("*/") ||
        trimmed.startsWith("//")
      );
    })
    .join("\n")
    .trim();
}

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

  it("keeps the tail of a token that holds a bracket out of the description", () => {
    // The same rule with another character that a token may hold: a run that
    // stopped at the bracket would leave the rest of the token in the
    // description, and the description reaches the client.
    const described = describeValue('GET https://digithings.ai/embed?token=xy7(zw8"qv9');
    expect(described).not.toContain("xy7");
    expect(described).not.toContain("zw8");
    expect(described).not.toContain("qv9");
    expect(described).toContain("https://digithings.ai/embed");
  });

  it("keeps the query string of a URL whose scheme is in upper case out of the description", () => {
    const described = describeValue("GET HTTPS://digithings.ai/embed?token=xy7");
    expect(described).not.toContain("xy7");
    expect(described).toContain("digithings.ai/embed");
  });

  it("keeps the redactor in step with the shared package", () => {
    // The redactor lives in three copies (the package, digichat and the
    // stack), because the two Workers do not depend on the package. One copy
    // that drifts is one copy that lets a token through, so the copies are
    // compared here. The doc comment around the code may differ; the code
    // may not.
    expect(
      redactorCode(path.join(repoRoot, "apps/digithings-stack-cloudflare/src/container-errors.ts")),
    ).toBe(
      redactorCode(path.join(repoRoot, "packages/durable-object-reconnect/src/index.ts")),
    );
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
    const response = containerUnavailableResponse("stack");
    expect(response.status).toBe(503);
    expect(response.headers.get("Retry-After")).toBe("5");
    const body = (await response.json()) as { code?: string; message?: string };
    expect(body.code).toBe(CONTAINER_UNAVAILABLE_CODE);
    expect(body.message).toContain("stack container unavailable");
    expect(body.message).toContain(CONTAINER_UNAVAILABLE_DETAIL);
  });

  it("does not carry the cause of the failure in the body", async () => {
    // The contract of the shared package (packages/durable-object-reconnect):
    // the cause of the failure is not in the body — a platform error can
    // carry a stack trace and a rejected value can carry internal detail, and
    // neither leaves the Worker. It is logged instead.
    const response = containerUnavailableResponse("stack");
    const text = await response.text();
    expect(text).not.toContain("token=");
    expect(text).not.toContain("s3cret");
    expect(text).not.toContain("the hop failed");
  });
});

describe("the answer keeps the rejected value out of the body", () => {
  it("does not carry the value the hop rejected with", async () => {
    // The value the hop rejected with is the cause. It goes into the log,
    // where the operator reads it, and it stays out of the answer the client
    // receives.
    const response = await fetchWithContainerRetry(async () => {
      throw "GET https://digithings.ai/embed?token=s3cret";
    });
    const text = await response.text();
    expect(text).not.toContain("s3cret");
    expect(text).not.toContain("digithings.ai");
    expect(text).not.toContain("embed");
  });

  it("does not carry the bare date the hop rejected with", async () => {
    // The production value (DIG-4928): a Date instance. Its rendering is the
    // bare date, and that is what the platform logs. The answer carries the
    // fixed detail, not the value.
    const response = await fetchWithContainerRetry(async () => {
      throw OPAQUE_REJECTION;
    });
    const text = await response.text();
    expect(text).not.toContain("Oct 21 2026");
    expect(text).not.toContain("2026");
  });
});

describe("the classification of a hop failure", () => {
  it("reads a value that is not an Error as unavailable, whatever its text says", () => {
    // The order of the checks is the contract, and it is pinned here
    // behaviourally. A thrown string that names a Durable Object renders like
    // an eviction, and a thrown string that names a rollout exit renders like
    // a failed container: neither is one. A value that is not an Error states
    // no failure of its own, so it is answered with the retryable
    // `container_unavailable` and it is not replayed.
    const evictionText =
      "Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.";
    expect(classifyContainerHopFailure(evictionText).kind).toBe("unavailable");
    expect(
      classifyContainerHopFailure("runtime signalled the container to exit: 143").kind,
    ).toBe("unavailable");
    expect(classifyContainerHopFailure(OPAQUE_REJECTION).kind).toBe("unavailable");
    expect(classifyContainerHopFailure({ code: "whatever" }).kind).toBe("unavailable");
  });

  it("does not read the message of a value that is not an Error", () => {
    // A plain object that carries a `message` property must not talk its way
    // into a classification it does not carry.
    const failure = classifyContainerHopFailure({
      message: "this Durable Object instance is no longer active",
    });
    expect(failure.kind).toBe("unavailable");
  });

  it("still reads a real Error that names an eviction as an eviction", () => {
    // The counterpart of the pin above: the eviction path is untouched for a
    // real Error, which is the shape the platform raises it in.
    const failure = classifyContainerHopFailure(
      new Error(
        "Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.",
      ),
    );
    expect(failure.kind).toBe("evicted");
  });

  it("still reads a real Error that names a failed container as failed", () => {
    const failure = classifyContainerHopFailure(
      new Error("Runtime signalled the container to exit due to a new version rollout: 143"),
    );
    expect(failure.kind).toBe("failed");
  });

  it("leaves a real Error that names neither alone", () => {
    // An unrelated failure is never masked: the caller rethrows it.
    expect(classifyContainerHopFailure(new Error("boom")).kind).toBe("unknown");
  });

  it("describes the value of an unavailable failure without its query string", () => {
    const failure = classifyContainerHopFailure(
      "GET https://digithings.ai/embed?token=s3cret",
    );
    expect(failure.kind).toBe("unavailable");
    if (failure.kind !== "unavailable") return;
    expect(failure.description).not.toContain("s3cret");
    expect(failure.description).toContain("digithings.ai/embed");
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
    const response = containerUnavailableResponse("stack");
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
    const response = containerUnavailableResponse("stack");
    expect(await isContainerRecycledResponse(response)).toBe(false);
  });

  it("makes the retry helper send the request exactly once", async () => {
    let attempts = 0;
    const response = await fetchWithContainerRetry(async () => {
      attempts += 1;
      return containerUnavailableResponse("stack");
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

  it("describes an Error whose message is not a string", () => {
    // The text is matched on, so it has to be a string. A message that is not
    // one must be described, not read: reading it would throw inside a catch
    // and turn the caught failure back into an uncaught one. The shared
    // package pins the same guard (packages/durable-object-reconnect).
    const odd = Object.assign(new Error("boom"), { message: 42 });
    expect(safeErrorMessage(odd)).toBe("42");
    const oddObject = Object.assign(new Error("boom"), { message: { code: 1 } });
    expect(safeErrorMessage(oddObject)).toBe("[object Object]");
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
