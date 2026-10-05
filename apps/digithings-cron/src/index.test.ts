import { afterEach, describe, expect, it, vi } from "vitest";
import worker from "./index";
import type { Env } from "./env";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function executionContext(promises: Promise<unknown>[]): ExecutionContext {
  return {
    waitUntil(promise: Promise<unknown>) {
      promises.push(promise);
    },
  } as unknown as ExecutionContext;
}

describe("scheduled", () => {
  it("lets dispatch failures reject through waitUntil", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("forbidden", { status: 403 })),
    );
    const pending: Promise<unknown>[] = [];
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };

    await worker.scheduled(
      {
        // token-canary stays workflow_dispatch. smoke-site is a probe and
        // treats HTTP 403 as a warning, so it cannot prove a dispatch failure.
        cron: "41 6 * * *",
        scheduledTime: Date.UTC(2026, 8, 4, 6, 17),
      } as ScheduledController,
      env,
      executionContext(pending),
    );

    expect(pending).toHaveLength(1);
    await expect(pending[0]).rejects.toThrow(/HTTP 403/);
  });

  it("dispatches Monday house-run-09 to digiquant-runner", async () => {
    const githubFetch = vi.fn();
    vi.stubGlobal("fetch", githubFetch);
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-house", status: "accepted" }, { status: 202 }),
    );
    const pending: Promise<unknown>[] = [];
    const scheduledTime = Date.UTC(2026, 9, 5, 9, 17);
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      RUNNER_AUTH_TOKEN: "runner-token",
      GITHUB_OVERRIDE_JOBS: "",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    await worker.scheduled(
      { cron: "17 9 * * MON", scheduledTime } as ScheduledController,
      env,
      executionContext(pending),
    );
    await Promise.all(pending);

    expect(githubFetch).not.toHaveBeenCalled();
    expect(runnerFetch).toHaveBeenCalledOnce();
  });

  it("does not dispatch disabled daily house-run retries", async () => {
    const githubFetch = vi.fn();
    vi.stubGlobal("fetch", githubFetch);
    const runnerFetch = vi.fn();
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      RUNNER_AUTH_TOKEN: "runner-token",
      GITHUB_OVERRIDE_JOBS: "",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    for (const cron of ["17 10 * * *", "17 11 * * *", "17 12 * * *"]) {
      const pending: Promise<unknown>[] = [];
      await worker.scheduled(
        { cron, scheduledTime: Date.UTC(2026, 9, 5, 10, 17) } as ScheduledController,
        env,
        executionContext(pending),
      );
      await Promise.all(pending);
      expect(pending).toHaveLength(0);
    }

    expect(githubFetch).not.toHaveBeenCalled();
    expect(runnerFetch).not.toHaveBeenCalled();
  });

  it("dispatches checkpoint-archive to digiquant-runner", async () => {
    const githubFetch = vi.fn();
    vi.stubGlobal("fetch", githubFetch);
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-archive", status: "accepted" }, { status: 202 }),
    );
    const pending: Promise<unknown>[] = [];
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      RUNNER_AUTH_TOKEN: "runner-token",
      GITHUB_OVERRIDE_JOBS: "",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    await worker.scheduled(
      { cron: "30 13 * * *", scheduledTime: Date.UTC(2026, 9, 5, 13, 30) } as ScheduledController,
      env,
      executionContext(pending),
    );
    await Promise.all(pending);

    expect(githubFetch).not.toHaveBeenCalled();
    expect(runnerFetch).toHaveBeenCalledOnce();
  });
});

const WINTER_BEFORE_OPEN = Date.UTC(2026, 0, 15, 13, 40, 0);

function kick(body: unknown, secret = "kick-secret"): Request {
  return new Request("https://digithings-cron/kick", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secret}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

describe("POST /kick", () => {
  it("skips the winter at-open cron before 09:30 ET", async () => {
    vi.spyOn(Date, "now").mockReturnValue(WINTER_BEFORE_OPEN);
    const runnerFetch = vi.fn();
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const res = await worker.fetch(
      kick({ cron: "40 13 * * MON-FRI" }),
      env,
      executionContext([]),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as { started: string[]; skipped: string[]; runs: unknown[] };
    expect(body.skipped).toEqual(["prices-at-open-13"]);
    expect(body.started).toEqual([]);
    expect(body.runs).toEqual([]);
    expect(runnerFetch).not.toHaveBeenCalled();
  });

  it("force starts the winter at-open cron and returns the run id", async () => {
    vi.spyOn(Date, "now").mockReturnValue(WINTER_BEFORE_OPEN);
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-open", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const res = await worker.fetch(
      kick({ cron: "40 13 * * MON-FRI", force: true }),
      env,
      executionContext([]),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      runs: { job_id: string; run_id: string; status: string }[];
    };
    expect(body.runs).toEqual([
      { job_id: "prices-at-open-13", run_id: "run-open", status: "accepted" },
    ]);
  });

  it("strips privileged house args from a kick without force", async () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.UTC(2026, 8, 30, 10, 0));
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-house", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(
      kick({
        cron: "17 9 * * MON",
        args: {
          refresh_scope: "all",
          dry_run: "true",
          resume_run_id: "prior-run",
          run_date: "2026-09-29",
        },
      }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    const [, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { args: Record<string, string> };
    expect(body.args).toEqual({
      refresh_scope: "none",
      run_date: "2026-09-30",
    });
  });

  it("keeps privileged house args and marks a forced kick", async () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.UTC(2026, 8, 30, 10, 0));
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-house", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(
      kick({
        cron: "17 9 * * MON",
        force: true,
        args: {
          refresh_scope: "all",
          dry_run: "true",
          resume_run_id: "prior-run",
          run_date: "2026-09-29",
        },
      }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    const [, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { args: Record<string, string> };
    expect(body.args).toEqual({
      refresh_scope: "all",
      dry_run: "true",
      resume_run_id: "prior-run",
      run_date: "2026-09-29",
      force: "true",
    });
  });

  it("kick without force strips dry_run", async () => {
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-archive", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(
      kick({
        cron: "30 13 * * *",
        args: { dry_run: "true" },
      }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    const [, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { args: Record<string, string> };
    expect(body.args).toEqual({});
  });

  // --- DIG-47.10 contract. Committed by the planner; these are the failing
  // tests the brief names. Do not edit them — make them pass.

  it("A.4 two kicks with the same startKey create one run", async () => {
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-house", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "s3cret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const kickExplicit = () =>
      worker.fetch(
        kick({ cron: "17 9 * * MON", startKey: "house-run-09:fixed" }, "s3cret"),
        env,
        executionContext([]),
      );

    const first = await kickExplicit();
    expect(first.status).toBe(200);
    expect(((await first.json()) as { started: string[] }).started).toEqual(["house-run-09"]);

    const second = await kickExplicit();
    expect(second.status).toBe(200);
    // The second kick resolves to the same start key, so it is a duplicate and
    // must not reach the runner.
    expect(runnerFetch).toHaveBeenCalledTimes(1);
  });

  it("a keyless kick still works, because four runbooks call it that way", async () => {
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-house", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "s3cret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(
      kick({ cron: "17 9 * * MON" }, "s3cret"),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ ok: true });
  });

  it("a non-numeric scheduledTime is rejected, never coerced to NaN", async () => {
    const env: Env = { DRY_RUN: "0", CRON_KICK_SECRET: "s3cret" };

    const res = await worker.fetch(
      kick({ cron: "17 9 * * MON", scheduledTime: "soon" }, "s3cret"),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(400);
    expect(((await res.json()) as { error: string }).error).toBe("invalid_args");
  });

  it("A.5 a keyless kick sends a minute-aligned scheduled time", async () => {
    // The 56_789 ms offset is deliberate and load-bearing. Every other clock in
    // this file is minute-aligned, so the floor under test is the identity on
    // all of them. Do not tidy this offset to match its neighbours: the guard
    // below turns that into a loud failure instead of a silent no-op.
    const requestedAt = Date.UTC(2026, 8, 30, 10, 37, 56, 789);
    expect(requestedAt % 60_000).not.toBe(0);
    // Also guard the hour: minute 37 is what distinguishes this floor from a
    // floor-to-the-hour, which would land on the same minute-aligned instant
    // and pass every assertion below.
    expect(Math.floor(requestedAt / 3_600_000) * 3_600_000).not.toBe(
      Math.floor(requestedAt / 60_000) * 60_000,
    );
    vi.spyOn(Date, "now").mockReturnValue(requestedAt);
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-kick", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(kick({ cron: "17 9 * * MON" }), env, executionContext([]));

    expect(res.status).toBe(200);
    const [, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { scheduled_time: number };
    // A.5 — a keyless kick derives its start from the request time floored to
    // the wall-clock minute, so a repeat inside the same minute collides on
    // purpose. A kick is a deliberately distinct namespace from the cron
    // path: it does not resolve to the cron's firing slot. See DIG-47 spec
    // section 9, decision D3.
    expect(body.scheduled_time % 60_000).toBe(0);
    expect(body.scheduled_time).toBe(Math.floor(requestedAt / 60_000) * 60_000);
  });

  it("kick with force keeps dry_run true", async () => {
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-archive", status: "accepted" }, { status: 202 }),
    );
    const env: Env = {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };

    const res = await worker.fetch(
      kick({
        cron: "30 13 * * *",
        force: true,
        args: { dry_run: "true" },
      }),
      env,
      executionContext([]),
    );

    expect(res.status).toBe(200);
    const [, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { args: Record<string, string> };
    expect(body.args.dry_run).toBe("true");
  });
});

describe("GET /runs", () => {
  it("proxies to the runner with RUNNER_AUTH_TOKEN", async () => {
    const runnerFetch = vi.fn(async () => Response.json({ run_id: "run-1", status: "running" }));
    const env: Env = {
      CRON_KICK_SECRET: "kick-secret",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const res = await worker.fetch(
      new Request("https://digithings-cron/runs/run-1", {
        headers: { Authorization: "Bearer kick-secret" },
      }),
      env,
      executionContext([]),
    );
    expect(res.status).toBe(200);
    const [url, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://digiquant-runner/v1/jobs/run-1");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer runner-token");
  });

  it("hides the route when CRON_KICK_SECRET is unset", async () => {
    const res = await worker.fetch(
      new Request("https://digithings-cron/runs/run-1"),
      {},
      executionContext([]),
    );
    expect(res.status).toBe(404);
  });
});
