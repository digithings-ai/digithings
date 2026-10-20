import { describe, expect, it } from "vitest";
import worker from "./index";
import type { Env } from "./env";
import {
  DURABLE_OBJECT_UNAVAILABLE,
  DurableObjectUnavailableError,
  errorMessage,
  fetchDurableObject,
  isDurableObjectGone,
  RECONNECT_RETRY_AFTER_SECONDS,
} from "./durable-object-reconnect";

/** The platform's own wording, quoted from the run-watch finding. */
const PLATFORM_GONE =
  "Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.";

function goneError(message = PLATFORM_GONE): Error {
  return new Error(message);
}

function jobRequest(token = "test-token"): Request {
  return new Request("https://digiquant-runner/v1/jobs", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      job_id: "market-data-refresh-morning",
      command: "market-data-refresh",
      args: {},
      concurrency: "market-data-refresh",
      timeout_seconds: 1800,
      code_ref: "main",
      cron: "0 13 * * *",
      scheduled_time: 1,
      idempotency_key: "market-data-refresh-morning:1",
    }),
  });
}

/** A RUNNER_CONTAINER binding whose stub answers with `fetch`. */
function envWith(fetchImpl: (request: Request) => Promise<Response>): Env {
  return {
    RUNNER_AUTH_TOKEN: "test-token",
    RUNNER_CONTAINER: {
      idFromName: (name: string) => name,
      get: () => ({ fetch: fetchImpl }),
    } as unknown as DurableObjectNamespace,
  } as unknown as Env;
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

  it("does not claim an unrelated failure", () => {
    expect(isDurableObjectGone(goneError("boom"))).toBe(false);
    expect(isDurableObjectGone(new Error(""))).toBe(false);
    expect(isDurableObjectGone(undefined)).toBe(false);
    expect(isDurableObjectGone({ message: PLATFORM_GONE })).toBe(false);
  });

  it("reads the message of a thrown value", () => {
    expect(errorMessage("plain text")).toBe("plain text");
    expect(errorMessage(goneError())).toBe(PLATFORM_GONE);
    expect(errorMessage({ message: "x" })).toBe("");
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
        return new Request("https://digiquant-runner/v1/jobs");
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
      () => new Request("https://digiquant-runner/v1/jobs"),
    );
    expect(res.status).toBe(200);
    expect(attempts).toBe(2);
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
        () => new Request("https://digiquant-runner/v1/jobs"),
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
        () => new Request("https://digiquant-runner/v1/jobs"),
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
        () => new Request("https://digiquant-runner/v1/jobs"),
      ),
    ).rejects.toBe(boom);
    expect(attempts).toBe(1);
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
        () => new Request("https://digiquant-runner/v1/jobs"),
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
      () => new Request("https://digiquant-runner/v1/jobs", { method: "POST", body: "payload" }),
    );
    expect(attempts).toBe(2);
    expect(seen).toEqual(["payload", "payload"]);
  });
});

describe("the worker answers 503 when the Durable Object is unreachable", () => {
  it("answers 503 with Retry-After on POST /v1/jobs", async () => {
    let attempts = 0;
    const res = await worker.fetch(
      jobRequest(),
      envWith(async () => {
        attempts += 1;
        throw goneError();
      }),
    );
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RECONNECT_RETRY_AFTER_SECONDS));
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe(DURABLE_OBJECT_UNAVAILABLE);
    expect(attempts).toBe(2);
  });

  it("answers 503 with Retry-After on GET /healthz", async () => {
    let attempts = 0;
    const res = await worker.fetch(
      new Request("https://digiquant-runner/healthz"),
      envWith(async () => {
        attempts += 1;
        throw goneError();
      }),
    );
    expect(res.status).toBe(503);
    expect(res.headers.get("Retry-After")).toBe(String(RECONNECT_RETRY_AFTER_SECONDS));
    expect(attempts).toBe(2);
  });

  it("serves the request when the reconnect recovers", async () => {
    let attempts = 0;
    const res = await worker.fetch(
      jobRequest(),
      envWith(async () => {
        attempts += 1;
        if (attempts === 1) throw goneError();
        return Response.json({ ok: true, run_id: "run-1", status: "accepted" }, { status: 202 });
      }),
    );
    expect(res.status).toBe(202);
    expect(attempts).toBe(2);
  });

  it("does not mask an unrelated failure", async () => {
    const boom = new Error("boom");
    await expect(
      worker.fetch(
        jobRequest(),
        envWith(async () => {
          throw boom;
        }),
      ),
    ).rejects.toBe(boom);
  });
});
