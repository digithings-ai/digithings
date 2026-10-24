import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";
import { decideAlert, SESSION_LABEL, SOURCE_LABEL, TRANSPORT_LABEL } from "./alerts";
import type { Env } from "./env";
import { handle, type RunResult } from "./worker";
import { RUNNER_UNAVAILABLE_DETAIL } from "./unavailable";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function env(over: Partial<Env> = {}): Env {
  return {
    RUNNER_AUTH_TOKEN: "runner-token",
    GH_ISSUES_TOKEN: "gh-token",
    DRY_RUN: "0",
    TWELVEX_CONTAINER: {} as DurableObjectNamespace,
    ...over,
  };
}

/**
 * The stub the Worker resolves for the Durable Object that owns the container.
 * The Worker takes a factory, so a reconnect can address a fresh stub.
 */
function stubOf(fetchImpl: unknown): () => Fetcher {
  return () => ({ fetch: fetchImpl } as unknown as Fetcher);
}

function post(route: string, body: unknown, token = "runner-token"): Request {
  return new Request(`https://twelvex-runner/run/${route}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "content-type": "application/json" },
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
    // The real argv lives in container/server.py. It is not copied here, and
    // no test asserts on it, so a placeholder keeps the shape of RunResult.
    command: ["not-asserted"],
    alert: "none",
    ...over,
  };
}

describe("routing and auth", () => {
  it("healthz does not call the container", async () => {
    const container = vi.fn();
    const res = await handle(new Request("https://twelvex-runner/healthz"), env(), stubOf(container));
    expect(res.status).toBe(200);
    expect(container).not.toHaveBeenCalled();
  });

  it("rejects a missing and a wrong token", async () => {
    const container = vi.fn();
    const binding = stubOf(container);
    const missing = await handle(post("heartbeat", {}), env({ RUNNER_AUTH_TOKEN: undefined }), binding);
    const wrong = await handle(post("heartbeat", {}, "other"), env(), binding);
    expect(missing.status).toBe(401);
    expect(wrong.status).toBe(401);
    expect(container).not.toHaveBeenCalled();
  });

  it("rejects an unknown route", async () => {
    const container = vi.fn();
    const res = await handle(post("other", {}), env(), stubOf(container));
    expect(res.status).toBe(404);
    expect(container).not.toHaveBeenCalled();
  });

  it("rejects ingest without a known bucket", async () => {
    const container = vi.fn();
    const res = await handle(post("ingest", { bucket: "hourly" }), env(), stubOf(container));
    expect(res.status).toBe(400);
    expect(container).not.toHaveBeenCalled();
  });

  it("rejects a session without a known session", async () => {
    const container = vi.fn();
    const res = await handle(post("session", { session: "hourly" }), env(), stubOf(container));
    expect(res.status).toBe(400);
    expect(container).not.toHaveBeenCalled();
  });

  it("rejects a run_date that is not a calendar date", async () => {
    const container = vi.fn();
    for (const runDate of ["2026-13-01", "2026-02-30", "20261020", "01-10-2026", "0000-01-01", 7]) {
      const res = await handle(
        post("session", { session: "asia", run_date: runDate }),
        env(),
        stubOf(container),
      );
      expect(res.status).toBe(400);
      expect(await res.json()).toEqual({ error: "invalid_run_date" });
    }
    expect(container).not.toHaveBeenCalled();
  });

  it("forwards a valid run_date on the session route", async () => {
    let forwarded: { run_date?: string } | undefined;
    const container = vi.fn(async (request: Request) => {
      forwarded = JSON.parse(await request.text()) as { run_date?: string };
      return Response.json(containerResult({ exit_code: 0 }));
    });
    const res = await handle(
      post("session", { job_id: "twelve-x-asia", session: "asia", run_date: "2026-10-01" }),
      env(),
      stubOf(container),
      vi.fn() as unknown as typeof fetch,
    );
    expect(res.status).toBe(200);
    expect(forwarded?.run_date).toBe("2026-10-01");
  });

  it("treats an empty run_date as absent, like the workflow default", async () => {
    let forwarded: { run_date?: string } | undefined;
    const container = vi.fn(async (request: Request) => {
      forwarded = JSON.parse(await request.text()) as { run_date?: string };
      return Response.json(containerResult({ exit_code: 0 }));
    });
    const res = await handle(
      post("session", { session: "asia", run_date: "" }),
      env(),
      stubOf(container),
      vi.fn() as unknown as typeof fetch,
    );
    expect(res.status).toBe(200);
    expect(forwarded?.run_date).toBeUndefined();
  });

  it("does not forward a run_date on the ingest route", async () => {
    let forwarded: { run_date?: string } | undefined;
    const container = vi.fn(async (request: Request) => {
      forwarded = JSON.parse(await request.text()) as { run_date?: string };
      return Response.json(containerResult({ exit_code: 0 }));
    });
    const res = await handle(
      post("ingest", { bucket: "daily", run_date: "2026-10-01" }),
      env(),
      stubOf(container),
      vi.fn() as unknown as typeof fetch,
    );
    expect(res.status).toBe(200);
    expect(forwarded?.run_date).toBeUndefined();
  });

  it("forwards a session with the session the workflow passes", async () => {
    let forwarded: { session: string; timeout_seconds: number } | undefined;
    const container = vi.fn(async (request: Request) => {
      forwarded = JSON.parse(await request.text()) as {
        session: string;
        timeout_seconds: number;
      };
      return Response.json(containerResult({ exit_code: 0 }));
    });
    const github = vi.fn();
    const res = await handle(
      post("session", { job_id: "twelve-x-asia", session: "asia" }),
      env(),
      stubOf(container),
      github as unknown as typeof fetch,
    );
    expect(res.status).toBe(200);
    expect(forwarded?.session).toBe("asia");
    expect(forwarded?.timeout_seconds).toBe(7200);
    expect(github).not.toHaveBeenCalled();
  });

  it("forwards ingest with the workflow bucket and auth", async () => {
    const container = vi.fn(async (_request: Request) =>
      Response.json(containerResult({ exit_code: 0 })),
    );
    const github = vi.fn();
    const res = await handle(
      post("ingest", { job_id: "twelve-x-market-context-daily", bucket: "daily" }),
      env(),
      stubOf(container),
      github as unknown as typeof fetch,
    );
    expect(res.status).toBe(200);
    const request = container.mock.calls[0][0] as Request;
    const forwarded = JSON.parse(await request.text()) as { bucket: string; dry_run: boolean };
    expect(forwarded.bucket).toBe("daily");
    expect(forwarded.dry_run).toBe(false);
    expect(github).not.toHaveBeenCalled();
  });

  it("DRY_RUN=1 still calls the container and does not write or alert", async () => {
    const container = vi.fn(async (_request: Request) =>
      Response.json(containerResult({ dry_run: true, log_tail: "dry_run ingest" })),
    );
    const github = vi.fn();
    const res = await handle(post("heartbeat", { job_id: "twelve-x-primemarket-heartbeat" }), env({ DRY_RUN: "1" }), stubOf(container), github as unknown as typeof fetch);
    expect(res.status).toBe(200);
    const body = (await res.json()) as RunResult;
    expect(body.dry_run).toBe(true);
    expect(body.alert).toBe("none");
    const request = container.mock.calls[0][0] as Request;
    const forwarded = JSON.parse(await request.text()) as { dry_run: boolean };
    expect(forwarded.dry_run).toBe(true);
    expect(github).not.toHaveBeenCalled();
  });
});

describe("the Durable Object hop", () => {
  it("answers 503 with the Retry-After when the instance was not available", async () => {
    // The container hop can reject with a value that is not an Error, and the
    // Durable Object then answers 503 with a Retry-After so the caller backs
    // off instead of hammering a runner that is still coming up (run-watch
    // DIG-4928). That answer is retryable, so it reaches the client with its
    // status and its header instead of being rewritten to a 502 that drops
    // the only instruction the caller needs.
    const container = vi.fn(async (_request: Request) =>
      new Response(
        JSON.stringify({
          error: "durable_object_unavailable",
          detail: RUNNER_UNAVAILABLE_DETAIL,
        }),
        {
          status: 503,
          headers: { "content-type": "application/json", "retry-after": "30" },
        },
      ),
    );
    const res = await handle(
      post("heartbeat", { job_id: "twelve-x-primemarket-heartbeat" }),
      env(),
      stubOf(container),
      vi.fn() as unknown as typeof fetch,
    );
    expect(res.status).toBe(503);
    expect(res.headers.get("retry-after")).toBe("30");
    const body = (await res.json()) as { error?: string; detail?: string };
    expect(body.error).toBe("durable_object_unavailable");
    // The Durable Object and the Worker answer the same contract, so the
    // detail is the one wording and not two copies of it.
    expect(body.detail).toBe(RUNNER_UNAVAILABLE_DETAIL);
  });

  it("still answers 502 when the container itself fails", async () => {
    const container = vi.fn(async (_request: Request) =>
      new Response("the container died", { status: 500 }),
    );
    const res = await handle(
      post("heartbeat", { job_id: "twelve-x-primemarket-heartbeat" }),
      env(),
      stubOf(container),
      vi.fn() as unknown as typeof fetch,
    );
    expect(res.status).toBe(502);
    expect(res.headers.get("retry-after")).toBeNull();
  });

  it("still answers 502 when the container answers 503 without the code of the Durable Object", async () => {
    // A 503 that does not come from the Durable Object is the container's own
    // answer (the @cloudflare/containers no-instance answer is a 503 whose
    // body is plain text), so it is a container failure and not an
    // unavailable instance. It must not be answered as the retryable one: a
    // caller that backs off on it would wait for an instance that is there.
    const container = vi.fn(async (_request: Request) =>
      new Response("There is no Container instance available at this time.", {
        status: 503,
        headers: { "content-type": "text/plain" },
      }),
    );
    const res = await handle(
      post("heartbeat", { job_id: "twelve-x-primemarket-heartbeat" }),
      env(),
      stubOf(container),
      vi.fn() as unknown as typeof fetch,
    );
    expect(res.status).toBe(502);
    expect(res.headers.get("retry-after")).toBeNull();
    expect(await res.json()).toEqual({ error: "container_failed" });
  });
});

describe("alerts", () => {
  it("ingest exit 2 stays quiet and exit 3 uses the transport label", () => {
    expect(
      decideAlert({ route: "ingest", exitCode: 2, reason: "auth", now: 0, open: [] }).action,
    ).toBe("none");
    const transport = decideAlert({
      route: "ingest",
      exitCode: 3,
      bucket: "intraday",
      reason: "timeout",
      now: Date.parse("2026-10-13T00:00:00Z"),
      open: [],
    });
    expect(transport).toMatchObject({ action: "create", label: TRANSPORT_LABEL });
    const source = decideAlert({
      route: "ingest",
      exitCode: 1,
      bucket: "daily",
      reason: "source: dmx",
      now: Date.parse("2026-10-13T00:00:00Z"),
      open: [],
    });
    expect(source).toMatchObject({ action: "create", label: SOURCE_LABEL });
  });

  it("comments inside the 24h window and escalates an unread heartbeat", () => {
    const now = Date.parse("2026-10-13T18:00:00Z");
    const decision = decideAlert({
      route: "heartbeat",
      exitCode: 1,
      reason: "session probe failed",
      now,
      open: [{ number: 270, createdAt: now - 13 * 60 * 60 * 1000, acknowledged: false }],
    });
    expect(decision).toMatchObject({
      action: "comment",
      label: SESSION_LABEL,
      number: 270,
      escalate: true,
    });
  });

  it("closes open session alerts only when the probe passes", () => {
    const now = Date.parse("2026-10-13T06:00:00Z");
    const closed = decideAlert({
      route: "heartbeat",
      exitCode: 0,
      reason: "ok",
      now,
      open: [{ number: 330, createdAt: now - 60_000, acknowledged: false }],
    });
    expect(closed).toMatchObject({ action: "close", numbers: [330], label: SESSION_LABEL });
    const failed = decideAlert({
      route: "heartbeat",
      exitCode: 1,
      reason: "rejected",
      now,
      open: [],
    });
    expect(failed).toMatchObject({ action: "create", label: SESSION_LABEL, assignees: ["chrizefan"] });
  });
});

describe("image pin", () => {
  it("pins the same twelve-x ref in the Dockerfile", () => {
    const ref = readFileSync(path.join(root, "twelvex-ref.txt"), "utf8").trim();
    const dockerfile = readFileSync(path.resolve(root, "../../infra/docker/Dockerfile.twelvex-runner"), "utf8");
    const toml = readFileSync(path.join(root, "wrangler.toml"), "utf8");
    expect(ref).toMatch(/^[0-9a-f]{40}$/);
    expect(dockerfile).toContain(ref);
    expect(toml).toContain('instance_type = "basic"');
    expect(toml).toContain("max_instances = 1");
    expect(dockerfile).not.toMatch(/ghp_|github_pat_/);
  });
});
