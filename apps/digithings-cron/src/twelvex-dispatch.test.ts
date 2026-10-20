import { afterEach, describe, expect, it, vi } from "vitest";
import type { Env } from "./env";
import { JOBS, type Job } from "./jobs";
import { dispatch } from "./dispatch";
import { dispatchTwelvex } from "./twelvex-dispatch";

afterEach(() => {
  vi.restoreAllMocks();
});

function ingestJob(): Job {
  const job = JOBS.find((row) => row.id === "twelve-x-market-context-intraday");
  if (!job) throw new Error("missing intraday job");
  return job;
}

describe("twelve-x runner jobs", () => {
  it("points ingest and heartbeat at twelvex-runner and leaves the other twelve-x rows on GitHub", () => {
    const moved = [
      ["twelve-x-market-context-intraday", "ingest", "intraday", "4 */4 * * *"],
      ["twelve-x-market-context-daily", "ingest", "daily", "30 5 * * *"],
      ["twelve-x-market-context-weekly", "ingest", "weekly", "8 7 * * SAT"],
      ["twelve-x-primemarket-heartbeat", "heartbeat", undefined, "3 6,18 * * *"],
    ] as const;
    for (const [id, route, bucket, cron] of moved) {
      const job = JOBS.find((row) => row.id === id);
      expect(job).toMatchObject({
        kind: "twelvex",
        route,
        cron,
        repo: "digithings-ai/twelve-x",
        ref: "develop",
        enabled: true,
      });
      expect(job?.workflow).toBeTruthy();
      if (bucket) expect(job?.inputs?.bucket).toBe(bucket);
    }
    for (const id of ["twelve-x-performance-eval", "twelve-x-archive-maintenance"]) {
      expect(JOBS.find((row) => row.id === id)?.kind).toBe("workflow_dispatch");
    }
  });

  it("points the FX research sessions at the runner with their session", () => {
    for (const [id, session, cron] of [
      ["twelve-x-asia", "asia", "7 0 * * MON-FRI"],
      ["twelve-x-london", "london", "12 7 * * MON-FRI"],
      ["twelve-x-new-york", "new_york", "17 12 * * MON-FRI"],
    ] as const) {
      expect(JOBS.find((row) => row.id === id)).toMatchObject({
        kind: "twelvex",
        route: "session",
        cron,
        repo: "digithings-ai/twelve-x",
        ref: "develop",
        enabled: true,
        timeoutSeconds: 7200,
        inputs: { session },
      });
    }
  });

  it("POSTs /run/session with the session the row carries", async () => {
    const runnerFetch = vi.fn(async (_request: Request) =>
      Response.json({ ok: true, exit_code: 0, duration_ms: 4, alert: "none" }),
    );
    const env: Env = {
      DRY_RUN: "0",
      RUNNER_AUTH_TOKEN: "runner-token",
      TWELVEX_RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const job = JOBS.find((row) => row.id === "twelve-x-asia");
    if (!job) throw new Error("missing asia job");
    const result = await dispatchTwelvex(env, job, job.cron);
    expect(result).toEqual({ ok: true, status: 200, dry_run: false });
    const request = runnerFetch.mock.calls[0][0] as Request;
    expect(request.url).toBe("https://twelvex-runner/run/session");
    const forwarded = JSON.parse(await request.text()) as { session: string; timeout_seconds: number };
    expect(forwarded.session).toBe("asia");
    expect(forwarded.timeout_seconds).toBe(7200);
  });

  it("dispatch sends the daily row to the runner", async () => {
    const runnerFetch = vi.fn(async (_request: Request) =>
      Response.json({ ok: true, exit_code: 0, duration_ms: 4, alert: "none" }),
    );
    const env: Env = {
      DRY_RUN: "0",
      RUNNER_AUTH_TOKEN: "runner-token",
      TWELVEX_RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const job = JOBS.find((row) => row.id === "twelve-x-market-context-daily");
    if (!job) throw new Error("missing daily job");
    const result = await dispatch(env, job, job.cron);
    expect(result).toEqual({ ok: true, status: 200, dry_run: false });
    const request = runnerFetch.mock.calls[0][0];
    expect(request.url).toBe("https://twelvex-runner/run/ingest");
  });
});

describe("dispatchTwelvex", () => {
  it("DRY_RUN=1 does not call the runner", async () => {
    const runnerFetch = vi.fn();
    const env: Env = {
      DRY_RUN: "1",
      TWELVEX_RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const result = await dispatchTwelvex(env, ingestJob(), ingestJob().cron);
    expect(result).toEqual({ ok: true, status: 0, dry_run: true });
    expect(runnerFetch).not.toHaveBeenCalled();
  });

  it("POSTs /run/ingest with the bucket and treats exit 0 as success", async () => {
    const runnerFetch = vi.fn(async (_request: Request) =>
      Response.json({ ok: true, exit_code: 0, duration_ms: 40, alert: "none", log_tail: "token=supersecret" }),
    );
    const env: Env = {
      DRY_RUN: "0",
      RUNNER_AUTH_TOKEN: "runner-token",
      TWELVEX_RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const job = ingestJob();
    const result = await dispatchTwelvex(env, job, job.cron);
    expect(result).toEqual({ ok: true, status: 200, dry_run: false });
    const request = runnerFetch.mock.calls[0][0];
    expect(request.url).toBe("https://twelvex-runner/run/ingest");
    expect(request.headers.get("Authorization")).toBe("Bearer runner-token");
    expect(JSON.parse(await request.text())).toMatchObject({
      job_id: "twelve-x-market-context-intraday",
      bucket: "intraday",
    });
  });

  it("treats ingest exit 2 as success and fails other exits without the log tail", async () => {
    const quiet = vi.fn(async () => Response.json({ ok: false, exit_code: 2, log_tail: "token=supersecret" }));
    const env: Env = {
      DRY_RUN: "0",
      RUNNER_AUTH_TOKEN: "runner-token",
      TWELVEX_RUNNER: { fetch: quiet } as unknown as Fetcher,
    };
    const job = ingestJob();
    await expect(dispatchTwelvex(env, job, job.cron)).resolves.toMatchObject({ ok: true, status: 200 });

    const failed = vi.fn(async () =>
      Response.json({ ok: false, exit_code: 1, log_tail: "token=supersecret" }),
    );
    env.TWELVEX_RUNNER = { fetch: failed } as unknown as Fetcher;
    await expect(dispatchTwelvex(env, job, job.cron)).rejects.toThrow("exit 1");
    await expect(dispatchTwelvex(env, job, job.cron)).rejects.toThrow(
      /^twelvex-runner twelve-x-market-context-intraday exit 1$/,
    );
  });

  it("prefers the twelve-x-only secret, and still accepts the shared token", async () => {
    const job = ingestJob();
    const makeRunner = () =>
      vi.fn(async (_request: Request) =>
        Response.json({ ok: true, exit_code: 0, duration_ms: 1, alert: "none" }),
      );

    // Dedicated secret wins even when the shared token is also set.
    const dedicated = makeRunner();
    await dispatchTwelvex(
      {
        DRY_RUN: "0",
        RUNNER_AUTH_TOKEN: "shared-token",
        TWELVEX_RUNNER_AUTH: "twelvex-token",
        TWELVEX_RUNNER: { fetch: dedicated } as unknown as Fetcher,
      },
      job,
      job.cron,
    );
    expect(dedicated.mock.calls[0][0].headers.get("Authorization")).toBe(
      "Bearer twelvex-token",
    );

    // Transitional fallback: a deployment holding only the shared token still works.
    const shared = makeRunner();
    await dispatchTwelvex(
      {
        DRY_RUN: "0",
        RUNNER_AUTH_TOKEN: "shared-token",
        TWELVEX_RUNNER: { fetch: shared } as unknown as Fetcher,
      },
      job,
      job.cron,
    );
    expect(shared.mock.calls[0][0].headers.get("Authorization")).toBe(
      "Bearer shared-token",
    );

    // The production shape: only the dedicated secret is set.
    const solo = makeRunner();
    await dispatchTwelvex(
      {
        DRY_RUN: "0",
        TWELVEX_RUNNER_AUTH: "twelvex-only",
        TWELVEX_RUNNER: { fetch: solo } as unknown as Fetcher,
      },
      job,
      job.cron,
    );
    expect(solo.mock.calls[0][0].headers.get("Authorization")).toBe(
      "Bearer twelvex-only",
    );

    // An empty dedicated secret falls back rather than sending `Bearer `.
    const empty = makeRunner();
    await dispatchTwelvex(
      {
        DRY_RUN: "0",
        TWELVEX_RUNNER_AUTH: "",
        RUNNER_AUTH_TOKEN: "shared-token",
        TWELVEX_RUNNER: { fetch: empty } as unknown as Fetcher,
      },
      job,
      job.cron,
    );
    expect(empty.mock.calls[0][0].headers.get("Authorization")).toBe(
      "Bearer shared-token",
    );
  });

  it("requires the auth token and the binding", async () => {
    const job = ingestJob();
    await expect(
      dispatchTwelvex({ DRY_RUN: "0" }, job, job.cron),
    ).rejects.toThrow("TWELVEX_RUNNER_AUTH or RUNNER_AUTH_TOKEN is required");
    await expect(
      dispatchTwelvex(
        { DRY_RUN: "0", RUNNER_AUTH_TOKEN: "runner-token" },
        job,
        job.cron,
      ),
    ).rejects.toThrow("TWELVEX_RUNNER service binding is required");
  });
});
