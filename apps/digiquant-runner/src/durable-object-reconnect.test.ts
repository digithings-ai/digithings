import { describe, expect, it } from "vitest";
import {
  DURABLE_OBJECT_UNAVAILABLE,
  RECONNECT_RETRY_AFTER_SECONDS,
} from "@digithings/durable-object-reconnect";
import worker from "./index";
import type { Env } from "./env";

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
    // The body is exactly this: the cause of the failure never leaves the
    // Worker, so a platform error or a stack trace cannot ride along.
    expect(await res.json()).toEqual({
      error: DURABLE_OBJECT_UNAVAILABLE,
      detail: "the runner's Durable Object instance was not available; retry later",
    });
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
