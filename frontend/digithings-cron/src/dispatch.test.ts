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
  ref: "main",
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
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 })),
    );
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };
    const result = await dispatch(env, baseJob, baseJob.cron);
    expect(result.ok).toBe(true);
    expect(result.status).toBe(204);
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

  it("POSTs repository_dispatch body", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    const job: Job = {
      id: "house-run-09",
      cron: "17 9 * * 1-5",
      repo: "digithings-ai/digithings",
      kind: "repository_dispatch",
      event_type: "olympus-daily",
      ref: "main",
      enabled: true,
    };
    const env: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "token" };
    await dispatch(env, job, job.cron);
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/dispatches");
    expect(JSON.parse(String(init.body))).toEqual({
      event_type: "olympus-daily",
      client_payload: {},
    });
  });
});
