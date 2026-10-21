/**
 * The container hop is the hop that fails when the platform closes the Durable
 * Object instance that owns the container (run-watch DIG-4753). This suite
 * pins the behaviour of the Worker around that hop.
 */
import { describe, expect, it, vi } from "vitest";
import {
  DURABLE_OBJECT_UNAVAILABLE,
  RECONNECT_RETRY_AFTER_SECONDS,
} from "@digithings/durable-object-reconnect";
import type { Env } from "./env";
import { handle, type RunResult } from "./worker";

/** The platform's own wording, quoted from the run-watch finding. */
const PLATFORM_GONE =
  "Connection closed: this Durable Object instance is no longer active. Reconnect or retry the request.";

function goneError(message = PLATFORM_GONE): Error {
  return new Error(message);
}

function env(over: Partial<Env> = {}): Env {
  return {
    RUNNER_AUTH_TOKEN: "runner-token",
    GH_ISSUES_TOKEN: "gh-token",
    DRY_RUN: "1",
    TWELVEX_CONTAINER: {} as DurableObjectNamespace,
    ...over,
  };
}

function heartbeat(body: unknown = {}): Request {
  return new Request("https://twelvex-runner/run/heartbeat", {
    method: "POST",
    headers: {
      Authorization: "Bearer runner-token",
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

function containerResult(over: Partial<RunResult> = {}): RunResult {
  return {
    ok: true,
    exit_code: 0,
    duration_ms: 12,
    log_tail: "",
    dry_run: false,
    command: ["python", "-m", "twelve_x.scripts.primemarket_session_heartbeat"],
    alert: "none",
    ...over,
  };
}

/**
 * The factory the Worker resolves the stub through. It counts the calls, so a
 * test can tell a reconnect (a second stub) from a retry on the same stub.
 */
function stubFactory(fetchImpl: (request: Request) => Promise<Response>): {
  connect: () => Fetcher;
  calls: () => number;
} {
  let calls = 0;
  return {
    connect: () => {
      calls += 1;
      return { fetch: fetchImpl } as unknown as Fetcher;
    },
    calls: () => calls,
  };
}

describe("the container hop when the platform closes the Durable Object instance", () => {
  it("reconnects once and serves the request", async () => {
    let attempts = 0;
    const stub = stubFactory(async () => {
      attempts += 1;
      if (attempts === 1) throw goneError();
      return Response.json(containerResult());
    });
    const res = await handle(heartbeat({ job_id: "twelve-x-primemarket-heartbeat" }), env(), stub.connect);
    expect(res.status).toBe(200);
    expect(attempts).toBe(2);
  });

  it("reconnects against a fresh stub, not the closed one", async () => {
    let attempts = 0;
    const stub = stubFactory(async () => {
      attempts += 1;
      if (attempts === 1) throw goneError();
      return Response.json(containerResult());
    });
    await handle(heartbeat(), env(), stub.connect);
    expect(stub.calls()).toBe(2);
  });

  it("forwards the body again on the reconnect", async () => {
    const bodies: string[] = [];
    let attempts = 0;
    const stub = stubFactory(async (request) => {
      attempts += 1;
      bodies.push(await request.text());
      if (attempts === 1) throw goneError();
      return Response.json(containerResult());
    });
    await handle(heartbeat({ job_id: "twelve-x-primemarket-heartbeat" }), env(), stub.connect);
    expect(attempts).toBe(2);
    expect(bodies).toHaveLength(2);
    const forwarded = JSON.parse(bodies[1]) as { job_id: string };
    expect(forwarded.job_id).toBe("twelve-x-primemarket-heartbeat");
  });

  it("answers 503 with Retry-After when the reconnect fails too", async () => {
    let attempts = 0;
    const stub = stubFactory(async () => {
      attempts += 1;
      throw goneError();
    });
    const res = await handle(heartbeat(), env(), stub.connect);
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

  it("logs the exit line when the instance stays unavailable", async () => {
    const lines: Record<string, unknown>[] = [];
    const spy = vi.spyOn(console, "log").mockImplementation((line: unknown) => {
      lines.push(JSON.parse(String(line)) as Record<string, unknown>);
    });
    try {
      const stub = stubFactory(async () => {
        throw goneError();
      });
      const res = await handle(heartbeat({ job_id: "twelve-x-primemarket-heartbeat" }), env(), stub.connect);
      expect(res.status).toBe(503);
    } finally {
      spy.mockRestore();
    }
    expect(lines).toContainEqual({
      job: "twelve-x-primemarket-heartbeat",
      route: "heartbeat",
      event: "exit",
      exit_code: null,
      error: DURABLE_OBJECT_UNAVAILABLE,
    });
  });

  it("does not retry a failure that is not a Durable Object close", async () => {
    let attempts = 0;
    const boom = new Error("boom");
    const stub = stubFactory(async () => {
      attempts += 1;
      throw boom;
    });
    await expect(handle(heartbeat(), env(), stub.connect)).rejects.toBe(boom);
    expect(attempts).toBe(1);
  });

  it("does not retry a container failure that answers with a status", async () => {
    let attempts = 0;
    const stub = stubFactory(async () => {
      attempts += 1;
      return new Response("busy", { status: 409 });
    });
    const res = await handle(heartbeat(), env(), stub.connect);
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ error: "busy" });
    expect(attempts).toBe(1);
  });

  it("answers 502 container_failed when the container fails", async () => {
    let attempts = 0;
    const stub = stubFactory(async () => {
      attempts += 1;
      return new Response("boom", { status: 500 });
    });
    const res = await handle(heartbeat(), env(), stub.connect);
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "container_failed" });
    expect(attempts).toBe(1);
  });

  it("answers 502 container_bad_json when the container answers nonsense", async () => {
    let attempts = 0;
    const stub = stubFactory(async () => {
      attempts += 1;
      return new Response("not json", { status: 200 });
    });
    const res = await handle(heartbeat(), env(), stub.connect);
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ error: "container_bad_json" });
    expect(attempts).toBe(1);
  });

  it("does not call the container for the health check", async () => {
    const stub = stubFactory(async () => Response.json(containerResult()));
    const res = await handle(new Request("https://twelvex-runner/healthz"), env(), stub.connect);
    expect(res.status).toBe(200);
    expect(stub.calls()).toBe(0);
  });
});
