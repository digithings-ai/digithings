import { afterEach, describe, expect, it, vi } from "vitest";
import {
  dispatch,
  KICK_ARG_NOT_ALLOWED,
  MISSING_REQUIRED_ARG,
  repositoryDispatchUrl,
  workflowDispatchUrl,
} from "./dispatch";
import type { Env } from "./env";
import { JOBS, jobsForCron, uniqueEnabledCrons, type Job } from "./jobs";

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

  it("treats a skipped container run as success", async () => {
    const runnerFetch = vi.fn(
      async () =>
        Response.json(
          { ok: true, run_id: "run-finished", status: "skipped" },
          { status: 202 },
        ),
    );
    const job: Job = {
      id: "house-run-09",
      cron: "17 9 * * *",
      repo: "digithings-ai/digithings",
      kind: "container",
      workflow: "pipeline-digiquant.yml",
      ref: "develop",
      command: "house-run",
      concurrency: "digiquant-pipeline",
      timeoutSeconds: 14400,
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
    expect(result.container_status).toBe("skipped");
    expect(result.run_id).toBe("run-finished");
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

  it("probe smoke-stack fetches healthz and does not call the runner or GitHub", async () => {
    const urls: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      urls.push(String(input));
      return Response.json({ ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);
    const runnerFetch = vi.fn();
    const job = JOBS.find((row) => row.id === "smoke-stack");
    expect(job?.kind).toBe("probe");
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "github-token",
      RUNNER_AUTH_TOKEN: "runner-token",
      GITHUB_OVERRIDE_JOBS: "",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const result = await dispatch(env, job as Job, job?.cron ?? "", 1);
    expect(result).toEqual({ ok: true, status: 200, dry_run: false });
    expect(urls).toEqual([
      "https://graph.digithings.ai/healthz",
      "https://key.digithings.ai/healthz",
      "https://search.digithings.ai/healthz",
    ]);
    expect(urls.some((url) => url.includes("api.github.com"))).toBe(false);
    expect(runnerFetch).not.toHaveBeenCalled();
  });

  it("DRY_RUN probe logs the url list and does not fetch", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    const runnerFetch = vi.fn();
    const job = JOBS.find((row) => row.id === "smoke-site") as Job;
    const env: Env = {
      DRY_RUN: "1",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const result = await dispatch(env, job, job.cron);
    expect(result).toEqual({ ok: true, status: 0, dry_run: true });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(runnerFetch).not.toHaveBeenCalled();
    const logged = logSpy.mock.calls.map((call) => String(call[0])).join("\n");
    expect(logged).toContain("https://digithings.ai/");
    expect(logged).toContain("https://digiquant.io/og.png");
    expect(logged).toContain("https://digiquant.io/build-info.json");
    expect(logged).not.toContain("api.github.com");
  });

  it("logs github_override and workflow_dispatch when a probe job id is listed", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const runnerFetch = vi.fn();
    const job = JOBS.find((row) => row.id === "smoke-site") as Job;
    const env: Env = {
      DRY_RUN: "0",
      GH_DISPATCH_TOKEN: "token",
      RUNNER_AUTH_TOKEN: "runner-token",
      GITHUB_OVERRIDE_JOBS: "smoke-site",
      RUNNER: { fetch: runnerFetch } as unknown as Fetcher,
    };
    const result = await dispatch(env, job, job.cron, 9);
    expect(result).toEqual({ ok: true, status: 204, dry_run: false });
    expect(runnerFetch).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("api.github.com");
    expect(url).toContain("smoke-site.yml");
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

describe("per-request dispatch args", () => {
  /** Dispatch through the real request path and return the JSON body sent. */
  async function sentBody(
    job: Job,
    args?: Record<string, string>,
  ): Promise<Record<string, unknown>> {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };
    await dispatch(env, job, job.cron, 0, args ? { args } : {});
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    return JSON.parse(String(init.body));
  }

  it("merges args over static inputs instead of replacing them", async () => {
    const job: Job = {
      ...baseJob,
      inputs: { backfill_snapshots: "true" },
    };
    expect(await sentBody(job, { dates: "2026-06-02" })).toEqual({
      ref: "develop",
      inputs: { backfill_snapshots: "true", dates: "2026-06-02" },
    });
  });

  it("keeps existing per-job inputs when args are supplied (DIG-69 regression)", async () => {
    // DIG-469 changed what a caller may send, so this test splits by row. Rows
    // that still accept a per-request key are kicked with one, and the original
    // assertion is unchanged: every static input the row declared is on the wire.
    // Rows that accept nothing can no longer reach the merge through /kick at
    // all — that is the allowlist working, not a regression — so they are
    // asserted as refusals below. The args-win merge contract itself stays
    // pinned by the two synthetic-job tests directly above, which use baseJob
    // (no kickArgs => unbounded) and are therefore untouched by DIG-469.
    const accepted: Record<string, string> = {
      "agent-pr-finalizer": "start_key",
      "twelve-x-archive-maintenance": "task",
    };
    for (const [id, key] of Object.entries(accepted)) {
      const job = JOBS.find((row) => row.id === id);
      expect(job, `missing ${id}`).toBeDefined();
      const body = await sentBody(job!, { [key]: "2026-06-02" });
      // Every static input the row already declared is still on the wire.
      for (const [inputKey, value] of Object.entries(job!.inputs ?? {})) {
        expect(body.inputs, `${id} lost ${inputKey}`).toMatchObject({ [inputKey]: value });
      }
    }
    // market_context_ingest declares no per-request input, so its rows accept
    // none. The static `bucket` is the row's identity and is never caller-set.
    for (const id of [
      "twelve-x-market-context-intraday",
      "twelve-x-market-context-daily",
      "twelve-x-market-context-weekly",
    ]) {
      const job = JOBS.find((row) => row.id === id);
      expect(job, `missing ${id}`).toBeDefined();
      expect(job!.kickArgs).toEqual([]);
      await expect(sentBody(job!, { dates: "2026-06-02" })).rejects.toThrow(
        /kick_arg_not_allowed/,
      );
    }
  });

  it("lets args override a static input of the same key", async () => {
    const job: Job = { ...baseJob, inputs: { dry_run: "false" } };
    expect(await sentBody(job, { dry_run: "true" })).toEqual({
      ref: "develop",
      inputs: { dry_run: "true" },
    });
  });

  it("works on a row that declares no static inputs", async () => {
    expect(await sentBody(baseJob, { dates: "2026-06-02" })).toEqual({
      ref: "develop",
      inputs: { dates: "2026-06-02" },
    });
  });

  it("sends {} when there are neither static inputs nor args", async () => {
    expect(await sentBody(baseJob)).toEqual({ ref: "develop", inputs: {} });
  });

  it("does not leak args into repository_dispatch client_payload", async () => {
    const job: Job = {
      id: "house-run-09",
      cron: "17 9 * * *",
      repo: "digithings-ai/digithings",
      kind: "repository_dispatch",
      event_type: "digiquant-baseline",
      enabled: true,
    };
    expect(await sentBody(job, { dates: "2026-06-02" })).toEqual({
      event_type: "digiquant-baseline",
      client_payload: {},
    });
  });

  it("reaches the request body in dry-run mode without calling fetch", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const logged: string[] = [];
    const logSpy = vi
      .spyOn(console, "log")
      .mockImplementation((line: unknown) => void logged.push(String(line)));
    const env: Env = { DRY_RUN: "1" };

    const result = await dispatch(env, baseJob, baseJob.cron, 0, {
      args: { dates: "2026-06-02" },
    });

    expect(result).toEqual({ ok: true, status: 0, dry_run: true });
    expect(fetchMock).not.toHaveBeenCalled();
    const line = JSON.parse(logged[0]) as { body: { inputs: unknown } };
    expect(line.body.inputs).toEqual({ dates: "2026-06-02" });
    logSpy.mockRestore();
  });
});

describe("twelve-x-snapshot-backfill trigger (DIG-55)", () => {
  const row = JOBS.find((job) => job.id === "twelve-x-snapshot-backfill");

  /** The ten remediation dates in severity order. Zero-padded ISO, required. */
  const BACKFILL_DATES = [
    "2026-06-02",
    "2026-06-05",
    "2026-06-08",
    "2026-06-11",
    "2026-06-16",
    "2026-06-10",
    "2026-06-25",
    "2026-06-29",
    "2026-06-30",
    "2026-07-10",
  ];

  async function backfillBody(args: Record<string, string>) {
    expect(row).toBeDefined();
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };
    await dispatch(env, row!, row!.cron, 0, { args });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    return { url, body: JSON.parse(String(init.body)) as Record<string, unknown> };
  }

  it("targets maintenance.yml on develop with backfill_snapshots set", async () => {
    expect(row).toMatchObject({
      id: "twelve-x-snapshot-backfill",
      repo: "digithings-ai/twelve-x",
      kind: "workflow_dispatch",
      workflow: "maintenance.yml",
      ref: "develop",
      enabled: false,
      cron: "0 0 30 2 *",
    });
    const { url, body } = await backfillBody({ dates: BACKFILL_DATES.join(",") });
    expect(url).toBe(
      "https://api.github.com/repos/digithings-ai/twelve-x/actions/workflows/maintenance.yml/dispatches",
    );
    expect(body).toEqual({
      ref: "develop",
      inputs: { backfill_snapshots: "true", dates: BACKFILL_DATES.join(",") },
    });
  });

  it("never fires on a clock: absent from enabled crons and wrangler triggers", async () => {
    expect(uniqueEnabledCrons()).not.toContain("0 0 30 2 *");
    expect(jobsForCron("0 0 30 2 *")).toEqual([]);
    // Reachable only on demand, via the same route as the paused house-run rows.
    expect(jobsForCron("0 0 30 2 *", { includeDisabled: true })).toEqual([row]);
    // 30 February cannot occur, so even `enabled: true` would never schedule.
    expect(
      uniqueEnabledCrons().some((cron) => cron === "0 0 30 2 *"),
    ).toBe(false);
  });

  it("carries no date bound in configuration; the guard, not the config, is the control", () => {
    // Nothing here is a bound — the row cannot be made safe by editing its
    // static inputs, because an operator can always omit them. `requiredKickArgs`
    // below is what refuses the bare kick.
    expect(row!.inputs).toEqual({ backfill_snapshots: "true" });
    for (const key of Object.keys(row!.inputs ?? {})) {
      expect(key).not.toMatch(/^(since|until|dates|run_date)$/);
    }
  });

  it("declares no input that could request fx_trade_ideas_snapshot pruning", () => {
    // Read from twelve-x develop at commit 1c7288d: maintenance.yml declares
    // `backfill_snapshots` and `since`; `until` and `dates` arrive with
    // twelve-x#237. There is no key that turns on trade-ideas recompute, and
    // backfill_snapshots.py reaches project_snapshots with trade_ideas=None, so
    // the trade-ideas _upsert returns on empty rows before its _prune.
    //
    // This asserts the ROW's declared inputs, which is configuration this repo
    // controls — a new key here fails the test. A key added to the row that
    // twelve-x does not declare would 422 at dispatch instead.
    //
    // When you add a key to twelve-x maintenance.yml, add it to
    // DECLARED_ON_TWELVE_X_DEVELOP here deliberately, with the commit you read.
    const DECLARED_ON_TWELVE_X_DEVELOP = [
      "backfill_snapshots",
      "since",
      "until",
      "dates",
    ];
    const declared = Object.keys(row!.inputs ?? {});
    for (const key of declared) {
      expect(
        DECLARED_ON_TWELVE_X_DEVELOP,
        `row declares ${key}, which maintenance.yml does not declare — it would 422`,
      ).toContain(key);
      expect(key).not.toMatch(/trade_?ideas/i);
    }
  });

  it("sends zero-padded ISO dates so the string compare cannot over-sweep", async () => {
    // maintenance.yml compares run_date as strings, so `2026-6-2` would sort
    // after every stored run_date and re-stamp/prune the whole table.
    for (const date of BACKFILL_DATES) {
      expect(date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(date).toBe(
        new Date(`${date}T00:00:00Z`).toISOString().slice(0, 10),
      );
    }
    const { body } = await backfillBody({ dates: BACKFILL_DATES.join(",") });
    expect((body.inputs as Record<string, string>).dates.split(",")).toHaveLength(10);
  });

  it("never sends an empty dates value, which maintenance.yml treats as an error", async () => {
    // `maintenance.yml` guards `[ -n "$DATES" ]`, which is true for a lone
    // space, so an empty string must be omitted rather than sent as "".
    const { body } = await backfillBody({ dates: BACKFILL_DATES.join(",") });
    expect(Object.keys(body.inputs as Record<string, string>)).not.toContain(
      "run_date",
    );
    expect((body.inputs as Record<string, string>).dates.trim()).not.toBe("");
  });
});

/**
 * DIG-369. Verified against twelve-x develop: `maintenance.yml` only passes
 * `--since` when the input is non-empty, and `backfill_snapshots.py` keeps
 * `distinct_run_dates()` in full when `since` is None. So a bare kick
 * re-projects EVERY stored run_date, each with a fresh `as_of=now`, and each
 * `_upsert` then prunes any older generation for that run_date. That is
 * production data on a live client, so the row now refuses it.
 */
describe("requiredKickArgs guard (DIG-369)", () => {
  const row = JOBS.find((job) => job.id === "twelve-x-snapshot-backfill");

  function stubGitHub(): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };

  async function kickRow(args: Record<string, string> | undefined, overrideEnv = env) {
    const fetchMock = stubGitHub();
    await dispatch(overrideEnv, row!, row!.cron, 0, args ? { args } : {});
    return fetchMock;
  }

  it("names every key that can carry a date bound, so #237 cannot be locked out", () => {
    expect(row?.requiredKickArgs).toEqual(["since", "dates", "until"]);
    // Exactly the key set maintenance.yml declares today plus the two that
    // twelve-x#237 (DIG-52) adds. No wider than that: a key that is not a date
    // bound must never satisfy the guard.
    for (const key of row!.requiredKickArgs!) {
      expect(key).toMatch(/^(since|dates|until)$/);
    }
    // No other row opts into the guard, so nothing else changes behaviour.
    const guarded = JOBS.filter((job) => job.requiredKickArgs !== undefined);
    expect(guarded.map((job) => job.id)).toEqual(["twelve-x-snapshot-backfill"]);
  });

  it("refuses a bare kick and never calls api.github.com", async () => {
    const fetchMock = stubGitHub();
    await expect(dispatch(env, row!, row!.cron, 0, {})).rejects.toThrow(
      /missing_required_arg/,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses an omitted args object entirely, which is what /kick sends bare", async () => {
    const fetchMock = stubGitHub();
    await expect(dispatch(env, row!, row!.cron, 0)).rejects.toThrow(
      /requires at least one of since, dates, until/,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["empty string", ""],
    ["single space", " "],
    ["padded spaces", "   "],
  ])("refuses a %s value, because a blank bound still sweeps the whole table", async (_label, value) => {
    // `maintenance.yml` guards `if [ -n "$SINCE" ]`, and " " is non-empty to
    // the shell, so a blank-but-present value would be passed through and then
    // sort below every stored run_date. Refusing it here is the point.
    const fetchMock = stubGitHub();
    await expect(dispatch(env, row!, row!.cron, 0, { args: { since: value } })).rejects.toThrow(
      /missing_required_arg/,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does NOT police the bound's format — presence only, on purpose", async () => {
    // A malformed-but-present bound still over-sweeps: "  2026-06-02  " sorts
    // below every stored run_date for the same reason an unpadded month does.
    // Rejecting it here would mean encoding a shape twelve-x#237 has not settled
    // yet, so this guard stays presence-only and the row documents the format.
    // Recorded as a known residual, not an oversight.
    for (const value of ["  2026-06-02  ", "2026-6-2", "not-a-date"]) {
      const fetchMock = await kickRow({ since: value });
      expect(fetchMock).toHaveBeenCalledTimes(1);
    }
  });

  it("refuses a kick whose only key is not a date bound", async () => {
    const fetchMock = stubGitHub();
    await expect(
      dispatch(env, row!, row!.cron, 0, { args: { backfill_snapshots: "false" } }),
    ).rejects.toThrow(/missing_required_arg/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each(["since", "dates", "until"])("dispatches with %s alone", async (key) => {
    const fetchMock = await kickRow({ [key]: "2026-06-02" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(init.body)) as { inputs: Record<string, string> };
    // The static input survives alongside the bound, and the row's own ref is used.
    expect(body.inputs).toEqual({ backfill_snapshots: "true", [key]: "2026-06-02" });
  });

  it("dispatches when the bound is only in the row's static inputs", async () => {
    // Proves the guard reads the MERGED inputs, not the args alone.
    const bound: Job = { ...baseJob, id: "bound-row", inputs: { since: "2026-06-02" }, requiredKickArgs: ["since"] };
    const fetchMock = stubGitHub();
    await dispatch(env, bound, bound.cron, 0, {});
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("is not a dry-run-only guard: DRY_RUN=1 refuses too, so the preview is faithful", async () => {
    const fetchMock = stubGitHub();
    await expect(
      dispatch({ DRY_RUN: "1" }, row!, row!.cron, 0, {}),
    ).rejects.toThrow(/missing_required_arg/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not touch repository_dispatch, which carries no inputs at all", async () => {
    const rd: Job = {
      ...baseJob,
      id: "rd-row",
      kind: "repository_dispatch",
      workflow: undefined,
      event_type: "something",
      requiredKickArgs: ["since"],
    };
    const fetchMock = stubGitHub();
    await dispatch(env, rd, rd.cron, 0, {});
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(repositoryDispatchUrl("digithings-ai/digithings"));
    expect(JSON.parse(String(init.body))).toEqual({ event_type: "something", client_payload: {} });
  });

  it("exports the stable prefix POST /kick maps to a 400", () => {
    // index.ts matches on this exact string; changing one without the other
    // silently turns a legible refusal back into an opaque 500.
    expect(MISSING_REQUIRED_ARG).toBe("missing_required_arg");
  });
});

/**
 * DIG-469. `dispatchGithub` merges per-request `/kick` args over the row's own
 * static inputs with args-win. That precedence stays: it is the contract
 * DIG-69/DIG-73 recorded, where `start_key` must be able to ADD a key the row
 * does not declare statically. The side effect was that the merge reached EVERY
 * workflow_dispatch row, so a holder of CRON_KICK_SECRET could rewrite a row's
 * own inputs — flip `dry_run` on agent-pr-finalizer, repoint `bucket` on a
 * market-context row. `kickArgs` is each row's own statement of which keys a
 * caller may supply, and it is checked before any fetch.
 */
describe("kickArgs allowlist (DIG-469)", () => {
  const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };

  function stubGitHub(): ReturnType<typeof vi.fn> {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  function row(id: string): Job {
    const found = JOBS.find((job) => job.id === id);
    if (!found) throw new Error(`missing ${id}`);
    return found;
  }

  async function sentBody(
    id: string,
    args?: Record<string, string>,
  ): Promise<{ ref: string; inputs: Record<string, string> }> {
    const fetchMock = stubGitHub();
    const job = row(id);
    await dispatch(env, job, job.cron, 0, args ? { args } : {});
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    return JSON.parse(String(init.body)) as { ref: string; inputs: Record<string, string> };
  }

  // Every row's own static inputs, and the key that must never become
  // caller-settable. These are the exact exposures the issue named.
  it.each([
    ["agent-pr-finalizer", "dry_run", "true"],
    ["twelve-x-market-context-intraday", "bucket", "weekly"],
    ["twelve-x-market-context-daily", "bucket", "weekly"],
    ["twelve-x-market-context-weekly", "bucket", "intraday"],
    ["twelve-x-archive-maintenance", "dry_run", "true"],
    ["twelve-x-archive-maintenance", "dump_before_prune", "false"],
    // twelve-x-snapshot-backfill is NOT in this table: a bare
    // `{backfill_snapshots}` kick carries no date bound, so requiredKickArgs
    // answers first. Its allowlist refusal is pinned below, with a valid bound
    // travelling alongside.
  ])("refuses %s being overridden via %s, and never calls api.github.com", async (id, key, value) => {
    const fetchMock = stubGitHub();
    const job = row(id);
    await expect(
      dispatch(env, job, job.cron, 0, { args: { [key]: value } }),
    ).rejects.toThrow(/kick_arg_not_allowed/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("still admits every key the row's workflow declares, and keeps the static input", async () => {
    // An allowlist must not become a place that silently drops a declared input.
    // Each of these workflows declares the key, and the row's own input rides
    // alongside it untouched.
    const admitted: [string, string, string][] = [
      ["agent-pr-finalizer", "start_key", "agent-pr-finalizer:1234"],
      ["twelve-x-archive-maintenance", "task", "prune"],
      ["twelve-x-archive-maintenance", "hot_days", "3"],
      ["twelve-x-performance-eval", "since", "2026-10-01"],
      ["twelve-x-digisearch-parity", "days", "30"],
      ["secret-staleness", "max_age_days", "60"],
    ];
    for (const [id, key, value] of admitted) {
      const body = await sentBody(id, { [key]: value });
      expect(body.inputs, `${id} refused its own declared key ${key}`).toMatchObject({
        [key]: value,
      });
      // The row's static config is never lost to the merge (DIG-69 regression).
      for (const [staticKey, staticValue] of Object.entries(row(id).inputs ?? {})) {
        expect(body.inputs, `${id} lost ${staticKey}`).toMatchObject({
          [staticKey]: staticValue,
        });
      }
    }
  });

  it("keeps the DIG-69/DIG-73 contract: args still ADD a key the row never declared", async () => {
    // Args-win is the point. `start_key` is absent from agent-pr-finalizer's
    // static inputs and the allowlist does not make it static — it lets the
    // caller supply it, which is how digithings-cron will dedupe runs.
    const job = row("agent-pr-finalizer");
    expect(job.inputs).not.toHaveProperty("start_key");
    const body = await sentBody("agent-pr-finalizer", { start_key: "agent-pr-finalizer:1234" });
    expect(body.inputs).toEqual({ dry_run: "false", start_key: "agent-pr-finalizer:1234" });
  });

  it("treats an empty allowlist as accepting nothing, while a bare kick still dispatches", async () => {
    const job = row("twelve-x-asia");
    expect(job.kickArgs).toEqual([]);
    const fetchMock = stubGitHub();
    await dispatch(env, job, job.cron, 0, {});
    expect(fetchMock).toHaveBeenCalledTimes(1);
    // ...and any arg at all is refused.
    await expect(dispatch(env, job, job.cron, 0, { args: { any: "thing" } })).rejects.toThrow(
      /kick_arg_not_allowed/,
    );
  });

  it("leaves an unbounded row unbounded, so a row with no opinion is not broken", async () => {
    // `undefined` is the documented escape hatch. No real row uses it — the
    // jobs.test.ts invariant forbids it — so this pins the default on a
    // synthetic row, which is also how the merge contract stays testable.
    const unbounded: Job = { ...baseJob, kickArgs: undefined };
    const fetchMock = stubGitHub();
    await dispatch(env, unbounded, unbounded.cron, 0, { args: { anything: "goes" } });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("is not a dry-run-only guard: DRY_RUN=1 refuses too, so the preview is faithful", async () => {
    const fetchMock = stubGitHub();
    await expect(
      dispatch({ DRY_RUN: "1" }, row("agent-pr-finalizer"), row("agent-pr-finalizer").cron, 0, {
        args: { dry_run: "true" },
      }),
    ).rejects.toThrow(/kick_arg_not_allowed/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("names the refused key and the accepted set, so the fix is obvious from the 400", async () => {
    const fetchMock = stubGitHub();
    await expect(
      dispatch(env, row("twelve-x-archive-maintenance"), row("twelve-x-archive-maintenance").cron, 0, {
        args: { dump_before_prune: "false", nope: "x" },
      }),
    ).rejects.toThrow(/refused dump_before_prune, nope.*accepts only task, hot_days/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("lets requiredKickArgs answer first, so DIG-369's refusal stays authoritative", async () => {
    // Order matters on the one row that carries both controls. A bare kick must
    // still read as missing_required_arg (it would sweep every run_date), not as
    // a vague allowlist complaint. A bounded-but-disallowed kick reads as the
    // allowlist. DIG-369 pins the first; DIG-469 pins the second.
    const job = row("twelve-x-snapshot-backfill");
    const bare = stubGitHub();
    await expect(dispatch(env, job, job.cron, 0, {})).rejects.toThrow(/missing_required_arg/);
    expect(bare).not.toHaveBeenCalled();

    const bounded = stubGitHub();
    await expect(
      dispatch(env, job, job.cron, 0, { args: { since: "2026-06-02", backfill_snapshots: "false" } }),
    ).rejects.toThrow(/kick_arg_not_allowed/);
    expect(bounded).not.toHaveBeenCalled();
  });

  it("does not touch repository_dispatch, which carries no inputs at all", async () => {
    const rd: Job = {
      ...baseJob,
      id: "rd-row",
      kind: "repository_dispatch",
      workflow: undefined,
      event_type: "something",
      kickArgs: [],
    };
    const fetchMock = stubGitHub();
    await dispatch(env, rd, rd.cron, 0, { args: { ignored: "yes" } });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(repositoryDispatchUrl("digithings-ai/digithings"));
    expect(JSON.parse(String(init.body))).toEqual({ event_type: "something", client_payload: {} });
  });

  it("exports the stable prefix POST /kick maps to a 400", () => {
    // index.ts matches on this exact string; changing one without the other
    // silently turns a legible refusal back into an opaque 500.
    expect(KICK_ARG_NOT_ALLOWED).toBe("kick_arg_not_allowed");
  });
});
