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

  // DIG-732: before this, an unmapped cron was one console.error line that
  // nobody read. A trigger that fires with nothing behind it is deployment
  // drift, so the tick must open an issue on the twelve-x path under the
  // unrecognised-cron label — never the missing-required-trigger label, which
  // means the opposite (a required cron is gone).
  it("raises the unrecognised-cron alarm when a tick maps to no job", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push({ url, init });
        // The alarm searches open issues for this class first, so the stub
        // answers that search honestly: nothing open yet.
        if (String(url).includes("/issues?")) return Response.json([], { status: 200 });
        const status = String(url).includes("/labels/") ? 200 : 201;
        return new Response(JSON.stringify({ html_url: "https://example.test/1" }), {
          status,
          headers: { "content-type": "application/json" },
        });
      }),
    );
    const pending: Promise<unknown>[] = [];
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "github-token" };

    await worker.scheduled(
      { cron: "13 4 * * *", scheduledTime: Date.UTC(2026, 8, 5, 4, 13) } as ScheduledController,
      env,
      executionContext(pending),
    );
    await Promise.all(pending);

    const issues = calls.filter((call) => call.url.endsWith("/issues"));
    expect(issues).toHaveLength(1);
    expect(issues[0].url).toBe("https://api.github.com/repos/digithings-ai/twelve-x/issues");
    const body = JSON.parse(String(issues[0].init?.body)) as {
      title: string;
      labels: string[];
      body: string;
    };
    expect(body.labels).toEqual(["cron-unrecognised-trigger"]);
    expect(body.title).toBe("Unrecognised cron trigger — 13 4 * * *");
    expect(body.body).toContain("13 4 * * *");
    // Only the issue write: an unmapped tick dispatches nothing.
    expect(calls.filter((call) => call.url.includes("/dispatches"))).toHaveLength(0);
  });

  it("opens one issue for six ticks of the same unmapped trigger, not six issues", async () => {
    // The flood this stops: an unmapped `13 4 * * *` (or any high-rate
    // trigger) is re-detected on every tick it fires. One open issue for the
    // drift is an alarm; six is the twelve-x #322 incident by another route.
    // This drives the real scheduled() path, not raiseViolationAlarms directly,
    // because the flood is a property of the tick, not of the alarm function.
    const created: string[] = [];
    let openIssues: { title: string; html_url: string }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (String(url).includes("/issues?")) return Response.json(openIssues, { status: 200 });
        if (String(url).includes("/labels/")) return new Response("{}", { status: 200 });
        if (String(url).endsWith("/issues")) {
          const body = JSON.parse(String(init?.body ?? "{}")) as { title: string };
          const html_url = `https://github.com/digithings-ai/twelve-x/issues/${7000 + created.length}`;
          created.push(body.title);
          openIssues = [...openIssues, { title: body.title, html_url }];
          return Response.json({ html_url }, { status: 201 });
        }
        return new Response("unexpected", { status: 500 });
      }),
    );
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "github-token" };

    for (let tick = 0; tick < 6; tick += 1) {
      const pending: Promise<unknown>[] = [];
      await worker.scheduled(
        {
          cron: "*/10 * * * *",
          scheduledTime: Date.UTC(2026, 8, 5, 4, 0, tick * 10),
        } as ScheduledController,
        env,
        executionContext(pending),
      );
      await Promise.all(pending);
    }

    expect(created).toEqual(["Unrecognised cron trigger — */10 * * * *"]);
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
