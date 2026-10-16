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
    for (const id of ["twelve-x-asia", "twelve-x-performance-eval", "twelve-x-archive-maintenance"]) {
      expect(JOBS.find((row) => row.id === id)?.kind).toBe("workflow_dispatch");
    }
  });

  it("dispatch sends the daily row to the runner", async () => {
    const runnerFetch = vi.fn(async () =>
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
    const request = runnerFetch.mock.calls[0][0] as Request;
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
    const runnerFetch = vi.fn(async () =>
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
    const request = runnerFetch.mock.calls[0][0] as Request;
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

  it("requires the auth token and the binding", async () => {
    const job = ingestJob();
    await expect(
      dispatchTwelvex({ DRY_RUN: "0" }, job, job.cron),
    ).rejects.toThrow("RUNNER_AUTH_TOKEN is required");
    await expect(
      dispatchTwelvex(
        { DRY_RUN: "0", RUNNER_AUTH_TOKEN: "runner-token" },
        job,
        job.cron,
      ),
    ).rejects.toThrow("TWELVEX_RUNNER service binding is required");
  });
});
