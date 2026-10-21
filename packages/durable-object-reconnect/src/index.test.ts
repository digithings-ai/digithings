import { describe, expect, it, vi } from "vitest";
import {
  DURABLE_OBJECT_UNAVAILABLE,
  durableObjectUnavailableResponse,
  DurableObjectUnavailableError,
  errorMessage,
  fetchDurableObject,
  isDurableObjectGone,
  isNonErrorRejection,
  RECONNECT_RETRY_AFTER_SECONDS,
} from "./index";

/** The platform's own wording, quoted from the run-watch findings. */
const PLATFORM_GONE =
  "Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.";

function goneError(message = PLATFORM_GONE): Error {
  return new Error(message);
}

function jobRequest(): Request {
  return new Request("https://runner.example/v1/jobs");
}

describe("isDurableObjectGone", () => {
  it("recognises the platform's own text", () => {
    expect(isDurableObjectGone(goneError())).toBe(true);
  });

  it("recognises the sibling shapes that name a Durable Object", () => {
    expect(isDurableObjectGone(goneError("Durable Object is gone."))).toBe(true);
    expect(
      isDurableObjectGone(goneError("Durable Object reset because its code was updated.")),
    ).toBe(true);
  });

  it("does not claim a container failure", () => {
    expect(isDurableObjectGone(goneError("container /run HTTP 409 already_running"))).toBe(false);
  });

  it("does not claim a container that says it is no longer active", () => {
    // The message does not name a Durable Object, so it is not an eviction of
    // the instance. Claiming it would retry a container failure and then
    // report it as an unavailable Durable Object.
    expect(isDurableObjectGone(goneError("the container is no longer active"))).toBe(false);
  });

  it("does not claim a Durable Object failure that is not a close", () => {
    expect(isDurableObjectGone(goneError("Durable Object storage quota exceeded"))).toBe(false);
  });

  it("does not claim an unrelated failure", () => {
    expect(isDurableObjectGone(goneError("boom"))).toBe(false);
    expect(isDurableObjectGone(new Error(""))).toBe(false);
    expect(isDurableObjectGone(undefined)).toBe(false);
    expect(isDurableObjectGone({ message: PLATFORM_GONE })).toBe(false);
  });

  it("reads the message of a thrown value", () => {
    expect(errorMessage("plain text")).toBe("plain text");
    expect(errorMessage(goneError())).toBe(PLATFORM_GONE);
    // A plain object is described, not believed: only an Error is read for its
    // message, so an object cannot talk its way into being an eviction.
    expect(errorMessage({ message: "x" })).toBe("[object Object]");
  });
});

describe("errorMessage", () => {
  it("describes a value that is not an Error and not a string", () => {
    // The platform records such a rejection with String(value), so this is
    // what an operator reads in the log. An empty string would leave nothing
    // at all (run-watch DIG-4928).
    expect(errorMessage(new Date("2026-10-21T11:51:44.000Z"))).toBe(
      String(new Date("2026-10-21T11:51:44.000Z")),
    );
    expect(errorMessage(undefined)).toBe("undefined");
    expect(errorMessage(null)).toBe("null");
    expect(errorMessage({})).toBe("[object Object]");
  });

  it("describes a value that refuses to be read as text", () => {
    const { proxy, revoke } = Proxy.revocable({}, {});
    revoke();
    // A description that throws would turn a caught failure back into an
    // uncaught one, so the description itself must never throw.
    expect(errorMessage(proxy)).toBe("[unreadable value]");
  });
});

describe("isNonErrorRejection", () => {
  it("recognises a rejection that is not an Error", () => {
    expect(isNonErrorRejection(new Date())).toBe(true);
    expect(isNonErrorRejection({})).toBe(true);
    expect(isNonErrorRejection("plain text")).toBe(true);
    expect(isNonErrorRejection(undefined)).toBe(true);
  });

  it("does not claim a real error", () => {
    expect(isNonErrorRejection(new Error("boom"))).toBe(false);
  });
});

describe("fetchDurableObject", () => {
  it("returns the first answer when the instance is there", async () => {
    let connects = 0;
    let requests = 0;
    const res = await fetchDurableObject(
      () => {
        connects += 1;
        return { fetch: async () => new Response("ok") };
      },
      () => {
        requests += 1;
        return jobRequest();
      },
    );
    expect(res.status).toBe(200);
    expect(connects).toBe(1);
    expect(requests).toBe(1);
  });

  it("reconnects when the first attempt says the instance is gone", async () => {
    let attempts = 0;
    const res = await fetchDurableObject(
      () => ({
        fetch: async () => {
          attempts += 1;
          if (attempts === 1) throw goneError();
          return new Response("ok");
        },
      }),
      () => jobRequest(),
    );
    expect(res.status).toBe(200);
    expect(attempts).toBe(2);
  });

  it("resolves a fresh stub for the reconnect", async () => {
    let connects = 0;
    await fetchDurableObject(
      () => {
        connects += 1;
        return {
          fetch: async () => {
            if (connects === 1) throw goneError();
            return new Response("ok");
          },
        };
      },
      () => jobRequest(),
    );
    expect(connects).toBe(2);
  });

  it("raises a retryable error when the reconnect fails as well", async () => {
    let attempts = 0;
    await expect(
      fetchDurableObject(
        () => ({
          fetch: async () => {
            attempts += 1;
            throw goneError();
          },
        }),
        () => jobRequest(),
      ),
    ).rejects.toBeInstanceOf(DurableObjectUnavailableError);
    expect(attempts).toBe(2);
  });

  it("keeps the platform error as the cause of the retryable error", async () => {
    const cause = goneError();
    let caught: unknown;
    try {
      await fetchDurableObject(
        () => ({
          fetch: async () => {
            throw cause;
          },
        }),
        () => jobRequest(),
      );
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(DurableObjectUnavailableError);
    const typed = caught as DurableObjectUnavailableError;
    expect(typed.retryable).toBe(true);
    expect(typed.lastError).toBe(cause);
    expect(typed.message).toBe(DURABLE_OBJECT_UNAVAILABLE);
  });

  it("does not reconnect an unrelated failure", async () => {
    let attempts = 0;
    const boom = new Error("boom");
    await expect(
      fetchDurableObject(
        () => ({
          fetch: async () => {
            attempts += 1;
            throw boom;
          },
        }),
        () => jobRequest(),
      ),
    ).rejects.toBe(boom);
    expect(attempts).toBe(1);
  });

  it("does not mask an unrelated failure that happens on the reconnect", async () => {
    // The first attempt says the instance is gone, so a reconnect is made. The
    // reconnect fails with a real error: that error must reach the caller, not
    // be reported as an unavailable Durable Object.
    let attempts = 0;
    const boom = new Error("boom on the reconnect");
    await expect(
      fetchDurableObject(
        () => ({
          fetch: async () => {
            attempts += 1;
            if (attempts === 1) throw goneError();
            throw boom;
          },
        }),
        () => jobRequest(),
      ),
    ).rejects.toBe(boom);
    expect(attempts).toBe(2);
  });

  it("reconnects when resolving the stub says the instance is gone", async () => {
    let connects = 0;
    const res = await fetchDurableObject(
      () => {
        connects += 1;
        if (connects === 1) throw goneError();
        return { fetch: async () => new Response("ok") };
      },
      () => jobRequest(),
    );
    expect(res.status).toBe(200);
    expect(connects).toBe(2);
  });

  it("raises a retryable error when resolving the stub keeps failing", async () => {
    let connects = 0;
    await expect(
      fetchDurableObject(
        () => {
          connects += 1;
          throw goneError();
        },
        () => jobRequest(),
      ),
    ).rejects.toBeInstanceOf(DurableObjectUnavailableError);
    expect(connects).toBe(2);
  });

  it("honours a single attempt when asked for one", async () => {
    let attempts = 0;
    await expect(
      fetchDurableObject(
        () => ({
          fetch: async () => {
            attempts += 1;
            throw goneError();
          },
        }),
        () => jobRequest(),
        { attempts: 1 },
      ),
    ).rejects.toBeInstanceOf(DurableObjectUnavailableError);
    expect(attempts).toBe(1);
  });

  it("rebuilds the request so a body is still readable on the reconnect", async () => {
    const seen: string[] = [];
    let attempts = 0;
    await fetchDurableObject(
      () => ({
        fetch: async (request: Request) => {
          attempts += 1;
          const text = await request.text();
          seen.push(text);
          if (attempts === 1) throw goneError();
          return new Response("ok");
        },
      }),
      () => new Request("https://runner.example/v1/jobs", { method: "POST", body: "payload" }),
    );
    expect(attempts).toBe(2);
    expect(seen).toEqual(["payload", "payload"]);
  });
});

describe("fetchDurableObject when the hop rejects with a value that is not an Error", () => {
  it("raises a retryable error instead of rethrowing the value unchanged", async () => {
    // The @cloudflare/containers package rethrows a non-Error rejection
    // verbatim, so a thrown Date used to reach the Worker unchanged and the
    // Worker's own guard never saw it (run-watch DIG-4928).
    const date = new Date("2026-10-21T11:51:44.000Z");
    let caught: unknown;
    try {
      await fetchDurableObject(
        () => ({
          fetch: async () => {
            throw date;
          },
        }),
        () => jobRequest(),
      );
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(DurableObjectUnavailableError);
    const typed = caught as DurableObjectUnavailableError;
    expect(typed.retryable).toBe(true);
    expect(typed.lastError).toBe(date);
    expect(typed.message).toBe(DURABLE_OBJECT_UNAVAILABLE);
  });

  it("raises a retryable error for a plain object too", async () => {
    const value = { code: "container_hop_failed" };
    let caught: unknown;
    try {
      await fetchDurableObject(
        () => ({
          fetch: async () => {
            throw value;
          },
        }),
        () => jobRequest(),
      );
    } catch (error) {
      caught = error;
    }
    expect(caught).toBeInstanceOf(DurableObjectUnavailableError);
    expect((caught as DurableObjectUnavailableError).lastError).toBe(value);
  });

  it("reconnects once before it gives up", async () => {
    let attempts = 0;
    await expect(
      fetchDurableObject(
        () => ({
          fetch: async () => {
            attempts += 1;
            throw new Date("2026-10-21T11:51:44.000Z");
          },
        }),
        () => jobRequest(),
      ),
    ).rejects.toBeInstanceOf(DurableObjectUnavailableError);
    expect(attempts).toBe(2);
  });

  it("serves the request when the reconnect recovers", async () => {
    let attempts = 0;
    const res = await fetchDurableObject(
      () => ({
        fetch: async () => {
          attempts += 1;
          if (attempts === 1) throw new Date("2026-10-21T11:51:44.000Z");
          return new Response("ok");
        },
      }),
      () => jobRequest(),
    );
    expect(res.status).toBe(200);
    expect(attempts).toBe(2);
  });

  it("logs the failure with a description, so the log is not a bare date", async () => {
    const logged: unknown[][] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      logged.push(args);
    });
    const date = new Date("2026-10-21T11:51:44.000Z");
    try {
      await expect(
        fetchDurableObject(
          () => ({
            fetch: async () => {
              throw date;
            },
          }),
          () => jobRequest(),
        ),
      ).rejects.toBeInstanceOf(DurableObjectUnavailableError);
    } finally {
      spy.mockRestore();
    }
    expect(logged.length).toBeGreaterThan(0);
    expect(logged.map((args) => args.join(" ")).join("\n")).toContain(String(date));
  });

  it("does not mask a real error that happens on the reconnect", async () => {
    const boom = new Error("boom on the reconnect");
    let attempts = 0;
    await expect(
      fetchDurableObject(
        () => ({
          fetch: async () => {
            attempts += 1;
            if (attempts === 1) throw new Date("2026-10-21T11:51:44.000Z");
            throw boom;
          },
        }),
        () => jobRequest(),
      ),
    ).rejects.toBe(boom);
    expect(attempts).toBe(2);
  });
});

describe("durableObjectUnavailableResponse", () => {
  it("answers 503 with Retry-After and the machine-readable code", async () => {
    const res = durableObjectUnavailableResponse("the instance was not available; retry later");
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RECONNECT_RETRY_AFTER_SECONDS));
    // The value the README and the Workers document, pinned as a literal: the
    // back-off window is a contract with the caller.
    expect(res.headers.get("Retry-After")).toBe("30");
    const body = (await res.json()) as { error: string; detail: string };
    expect(body.error).toBe(DURABLE_OBJECT_UNAVAILABLE);
    expect(body.detail).toBe("the instance was not available; retry later");
  });
});
