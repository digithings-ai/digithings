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
        // smoke-site stays workflow_dispatch. research-metrics is a container job.
        cron: "17 6 * * *",
        scheduledTime: Date.UTC(2026, 8, 4, 6, 17),
      } as ScheduledController,
      env,
      executionContext(pending),
    );

    expect(pending).toHaveLength(1);
    await expect(pending[0]).rejects.toThrow(/HTTP 403/);
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
