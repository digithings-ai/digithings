import { afterEach, describe, expect, it, vi } from "vitest";
import {
  dispatch,
  repositoryDispatchUrl,
  workflowDispatchUrl,
} from "./dispatch";
import type { Env } from "./env";
import type { Job } from "./jobs";

const baseJob: Job = {
  id: "test-job",
  cron: "5 22 * * *",
  repo: "digithings-ai/digithings",
  kind: "workflow_dispatch",
  workflow: "pipeline-research-metrics.yml",
  ref: "develop",
  enabled: true,
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("URL builders", () => {
  it("builds workflow_dispatch URL", () => {
    expect(
      workflowDispatchUrl("digithings-ai/digithings", "pipeline-research-metrics.yml"),
    ).toBe(
      "https://api.github.com/repos/digithings-ai/digithings/actions/workflows/pipeline-research-metrics.yml/dispatches",
    );
  });

  it("builds repository_dispatch URL", () => {
    expect(repositoryDispatchUrl("digithings-ai/digithings")).toBe(
      "https://api.github.com/repos/digithings-ai/digithings/dispatches",
    );
  });
});

describe("dispatch", () => {
  it("DRY_RUN=1 does not call fetch", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = { DRY_RUN: "1" };
    const result = await dispatch(env, baseJob, baseJob.cron);
    expect(result).toEqual({ ok: true, status: 0, dry_run: true });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("treats 204 as success", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };
    const result = await dispatch(env, baseJob, baseJob.cron);
    expect(result.ok).toBe(true);
    expect(result.status).toBe(204);
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ ref: "develop", inputs: {} });
  });

  it("requires a token outside dry-run mode", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = { DRY_RUN: "0" };

    await expect(dispatch(env, baseJob, baseJob.cron)).rejects.toThrow(
      "GH_DISPATCH_TOKEN is required",
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("treats 422 already running as success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ message: "Workflow is already running" }), {
            status: 422,
          }),
      ),
    );
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };
    const result = await dispatch(env, baseJob, baseJob.cron);
    expect(result.ok).toBe(true);
    expect(result.status).toBe(422);
  });

  it("throws on other errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("forbidden", { status: 403 })),
    );
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };
    await expect(dispatch(env, baseJob, baseJob.cron)).rejects.toThrow(/403/);
  });

  it("retries rate limits instead of reporting success", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response("secondary rate limit", {
          status: 429,
          headers: { "Retry-After": "0" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };

    const result = await dispatch(env, baseJob, baseJob.cron);

    expect(result.status).toBe(204);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("uses attempt backoff when Retry-After is absent", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("secondary rate limit", { status: 429 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const timeoutSpy = vi
      .spyOn(globalThis, "setTimeout")
      .mockImplementation(((callback: () => void) => {
        callback();
        return 0;
      }) as unknown as typeof setTimeout);
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };

    const result = await dispatch(env, baseJob, baseJob.cron);

    expect(result.status).toBe(204);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(timeoutSpy).toHaveBeenCalledWith(expect.any(Function), 1_000);
  });

  it("POSTs a container job to the runner and does not call GitHub", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const runnerFetch = vi.fn(
      async () =>
        Response.json({ ok: true, run_id: "run-1", status: "accepted" }, { status: 202 }),
    );
    const job: Job = {
      id: "market-data-refresh-morning",
      cron: "0 13 * * *",
      repo: "digithings-ai/digithings",
      kind: "container",
      workflow: "pipeline-market-data-refresh.yml",
      ref: "develop",
      command: "market-data-refresh",
      concurrency: "market-data-refresh",
      timeoutSeconds: 1800,
      codeRef: "main",
      enabled: true,
    };
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      RUNNER_AUTH_TOKEN: "runner-token",
      GITHUB_OVERRIDE_JOBS: "",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const result = await dispatch(env, job, job.cron, 1_700_000_000_000);
    expect(result).toEqual({
      ok: true,
      status: 202,
      dry_run: false,
      run_id: "run-1",
      container_status: "accepted",
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(runnerFetch).toHaveBeenCalledOnce();
    const [url, init] = runnerFetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://digiquant-runner/v1/jobs");
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer runner-token");
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body).toEqual({
      job_id: "market-data-refresh-morning",
      command: "market-data-refresh",
      args: {},
      concurrency: "market-data-refresh",
      timeout_seconds: 1800,
      code_ref: "main",
      cron: "0 13 * * *",
      scheduled_time: 1_700_000_000_000,
      idempotency_key: "market-data-refresh-morning:1700000000000",
    });
    expect(JSON.stringify(body)).not.toContain("runner-token");
    expect(JSON.stringify(body)).not.toContain("RUNNER_AUTH_TOKEN");
  });

  it("treats runner already_running as success", async () => {
    const runnerFetch = vi.fn(
      async () =>
        Response.json(
          { ok: true, run_id: "run-held", status: "already_running" },
          { status: 202 },
        ),
    );
    const job: Job = {
      id: "prices-fx-refresh",
      cron: "19 */2 * * MON-FRI",
      repo: "digithings-ai/digithings",
      kind: "container",
      workflow: "pipeline-digiquant-prices.yml",
      ref: "develop",
      command: "prices-fx-candles",
      concurrency: "digiquant-fx-candles",
      timeoutSeconds: 600,
      codeRef: "main",
      enabled: true,
    };
    const env: Env = {
      DRY_RUN: "0",
      RUNNER_AUTH_TOKEN: "runner-token",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const result = await dispatch(env, job, job.cron, 42);
    expect(result.ok).toBe(true);
    expect(result.container_status).toBe("already_running");
    expect(result.run_id).toBe("run-held");
  });

  it("requires RUNNER_AUTH_TOKEN and does not call the runner without it", async () => {
    const runnerFetch = vi.fn();
    const job: Job = {
      id: "prices-eod-macro",
      cron: "27 21 * * MON-FRI",
      repo: "digithings-ai/digithings",
      kind: "container",
      workflow: "pipeline-digiquant-prices.yml",
      ref: "develop",
      command: "prices-eod-macro",
      concurrency: "digiquant-eod-macro",
      timeoutSeconds: 1200,
      codeRef: "main",
      enabled: true,
    };
    const env: Env = {
      DRY_RUN: "0",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    await expect(dispatch(env, job, job.cron, 1)).rejects.toThrow(
      "RUNNER_AUTH_TOKEN is required",
    );
    expect(runnerFetch).not.toHaveBeenCalled();
  });

  it("logs github_override and uses workflow_dispatch when the job id is listed", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const runnerFetch = vi.fn();
    const job: Job = {
      id: "market-data-refresh-evening",
      cron: "30 21 * * *",
      repo: "digithings-ai/digithings",
      kind: "container",
      workflow: "pipeline-market-data-refresh.yml",
      inputs: {},
      ref: "develop",
      command: "market-data-refresh",
      concurrency: "market-data-refresh",
      timeoutSeconds: 1800,
      codeRef: "main",
      enabled: true,
    };
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "token",
      RUNNER_AUTH_TOKEN: "runner-token",
      GITHUB_OVERRIDE_JOBS: "market-data-refresh-evening, prices-eod-macro",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const result = await dispatch(env, job, job.cron, 9);
    expect(result).toEqual({ ok: true, status: 204, dry_run: false });
    expect(runnerFetch).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledOnce();
    const logged = errorSpy.mock.calls.map((call) => String(call[0])).join("\n");
    expect(logged).toContain('"github_override":true');
    expect(logged).toContain('"error":"github_override"');
  });

  it("POSTs repository_dispatch body", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const job: Job = {
      id: "house-run-09",
      cron: "17 9 * * *",
      repo: "digithings-ai/digithings",
      kind: "repository_dispatch",
      event_type: "digiquant-baseline",
      enabled: true,
    };
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };
    await dispatch(env, job, job.cron);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/dispatches");
    expect(JSON.parse(String(init.body))).toEqual({
      event_type: "digiquant-baseline",
      client_payload: {},
    });
  });
});
