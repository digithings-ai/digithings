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

/**
 * DIG-369. The sentinel cron is reachable only from here, and a kick with no
 * date bound would re-project every stored run_date on twelve-x. The refusal
 * must be legible: an operator who gets an opaque 500 retries, and the second
 * attempt is the expensive one.
 */
describe("POST /kick refuses an unbounded backfill (DIG-369)", () => {
  const SENTINEL = "0 0 30 2 *";

  function envFor(githubFetch: () => Promise<Response>): Env {
    return {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      GH_DISPATCH_TOKEN: "github-token",
      GITHUB_OVERRIDE_JOBS: "",
      RUNNER_AUTH_TOKEN: "runner-token",
    } as Env;
  }

  it("answers 400 missing_required_arg on a bare kick, and never dispatches", async () => {
    const githubFetch = vi.fn();
    vi.stubGlobal("fetch", githubFetch);
    const env = envFor(githubFetch as unknown as () => Promise<Response>);
    env.RUNNER = undefined;
    const res = await worker.fetch(kick({ cron: SENTINEL }), env, executionContext([]));
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string; detail: string };
    expect(body.error).toBe("missing_required_arg");
    expect(body.detail).toContain("since");
    // The whole point: no workflow_dispatch reached GitHub.
    expect(githubFetch).not.toHaveBeenCalled();
  });

  it.each([
    ["empty since", { since: "" }],
    ["blank since", { since: "   " }],
    ["a non-date key", { backfill_snapshots: "true" }],
  ])("refuses %s the same way", async (_label, args) => {
    const githubFetch = vi.fn();
    vi.stubGlobal("fetch", githubFetch);
    const env = envFor(githubFetch as unknown as () => Promise<Response>);
    env.RUNNER = undefined;
    const res = await worker.fetch(kick({ cron: SENTINEL, args }), env, executionContext([]));
    expect(res.status).toBe(400);
    expect(((await res.json()) as { error: string }).error).toBe("missing_required_arg");
    expect(githubFetch).not.toHaveBeenCalled();
  });

  it("dispatches once a date bound is present", async () => {
    const githubFetch = vi.fn(
      async () => new Response(null, { status: 204 }),
    );
    vi.stubGlobal("fetch", githubFetch);
    const env = envFor(githubFetch as unknown as () => Promise<Response>);
    env.RUNNER = undefined;
    const res = await worker.fetch(
      kick({ cron: SENTINEL, args: { since: "2026-06-02" } }),
      env,
      executionContext([]),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as { ok: boolean; started: string[] };
    expect(body.ok).toBe(true);
    expect(body.started).toEqual(["twelve-x-snapshot-backfill"]);
    const [url, init] = githubFetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("maintenance.yml/dispatches");
    expect(JSON.parse(String(init.body))).toEqual({
      ref: "develop",
      inputs: { backfill_snapshots: "true", since: "2026-06-02" },
    });
  });
});

/**
 * DIG-469. A `/kick` that names a key its row does not accept must read as a
 * deliberate refusal. An opaque 500 is what an operator retries blind, and on
 * this row the retry is the expensive one: `dry_run` on agent-pr-finalizer is
 * live dispatch, not a rehearsal.
 */
describe("POST /kick refuses a non-allowlisted arg (DIG-469)", () => {
  const FINALIZER = "11 7 * * *";

  function envFor(): Env {
    return {
      DRY_RUN: "0",
      CRON_KICK_SECRET: "kick-secret",
      GH_DISPATCH_TOKEN: "github-token",
      GITHUB_OVERRIDE_JOBS: "",
    } as Env;
  }

  it("answers 400 kick_arg_not_allowed and never dispatches", async () => {
    const githubFetch = vi.fn();
    vi.stubGlobal("fetch", githubFetch);
    const res = await worker.fetch(
      kick({ cron: FINALIZER, args: { dry_run: "true" } }),
      envFor(),
      executionContext([]),
    );
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string; detail: string };
    expect(body.error).toBe("kick_arg_not_allowed");
    // The detail names the key, so the operator does not have to guess.
    expect(body.detail).toContain("dry_run");
    expect(githubFetch).not.toHaveBeenCalled();
  });

  it("still lets start_key through, and still sends dry_run: false", async () => {
    // The normal path is untouched: a kick with no args, and a kick carrying the
    // one key this row accepts, both dispatch with the row's own config intact.
    const githubFetch = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", githubFetch);
    const res = await worker.fetch(
      kick({ cron: FINALIZER, args: { start_key: "agent-pr-finalizer:1234" } }),
      envFor(),
      executionContext([]),
    );
    expect(res.status).toBe(200);
    const [, init] = githubFetch.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { inputs: Record<string, string> };
    expect(body.inputs).toEqual({ dry_run: "false", start_key: "agent-pr-finalizer:1234" });
  });

  it("keeps DIG-369's missing_required_arg answer on the row that carries both controls", async () => {
    // Cross-check from the HTTP side: requiredKickArgs still answers first, so
    // the DIG-369 test contract holds through the real request path.
    const githubFetch = vi.fn();
    vi.stubGlobal("fetch", githubFetch);
    const res = await worker.fetch(
      kick({ cron: "0 0 30 2 *" }),
      envFor(),
      executionContext([]),
    );
    expect(res.status).toBe(400);
    expect(((await res.json()) as { error: string }).error).toBe("missing_required_arg");
    expect(githubFetch).not.toHaveBeenCalled();
  });
});
