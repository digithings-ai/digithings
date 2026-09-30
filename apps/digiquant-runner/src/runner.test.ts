import { describe, expect, it } from "vitest";
import worker from "./index";
import { dataPlaneEnv, type Env } from "./env";
import {
  HEARTBEAT_MS,
  RunnerSession,
  memoryKv,
  type ContainerPort,
  type ContainerStatus,
  type RunJobRequest,
} from "./runner-session";

function job(over: Partial<RunJobRequest> = {}): RunJobRequest {
  return {
    job_id: "market-data-refresh-morning",
    command: "market-data-refresh",
    args: {},
    concurrency: "market-data-refresh",
    timeout_seconds: 1800,
    code_ref: "main",
    cron: "0 13 * * *",
    scheduled_time: 1,
    idempotency_key: "market-data-refresh-morning:1",
    ...over,
  };
}

function post(body: RunJobRequest, token = "test-token"): Request {
  return new Request("https://digiquant-runner/v1/jobs", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(body),
  });
}

function harness(): {
  session: RunnerSession;
  starts: string[];
  alarms: number[];
  statuses: Map<string, ContainerStatus>;
} {
  const starts: string[] = [];
  const alarms: number[] = [];
  const statuses = new Map<string, ContainerStatus>();
  const port: ContainerPort = {
    async startRun(body) {
      starts.push(body.run_id);
      statuses.set(body.run_id, {
        status: "running",
        exit_code: null,
        started_at: "2026-09-29T13:00:00.000Z",
        finished_at: null,
        git_sha: "abc123",
        log_tail: "",
      });
    },
    async readStatus(runId) {
      return statuses.get(runId) ?? null;
    },
  };
  const session = new RunnerSession({
    kv: memoryKv(),
    port,
    scheduleAlarm: async (delayMs) => {
      alarms.push(delayMs);
    },
    now: () => Date.parse("2026-09-29T13:00:00.000Z"),
  });
  return { session, starts, alarms, statuses };
}

function envFor(session: RunnerSession): Env {
  return {
    RUNNER_AUTH_TOKEN: "test-token",
    RUNNER_CONTAINER: {
      idFromName: (name: string) => name,
      get: () => ({ fetch: (request: Request) => session.fetch(request) }),
    } as unknown as DurableObjectNamespace,
  };
}

describe("digiquant-runner worker", () => {
  it("rejects POST /v1/jobs without the bearer", async () => {
    const { session } = harness();
    const res = await worker.fetch(post(job(), ""), envFor(session));
    expect(res.status).toBe(401);
  });

  it("rejects an unknown command", async () => {
    const { session, starts } = harness();
    const res = await worker.fetch(
      post(job({ command: "house-run", concurrency: "digiquant-pipeline" })),
      envFor(session),
    );
    expect(res.status).toBe(400);
    expect(starts).toHaveLength(0);
  });

  it("returns the same run_id for a duplicate idempotency key and starts once", async () => {
    const { session, starts } = harness();
    const env = envFor(session);
    const first = await worker.fetch(post(job()), env);
    const second = await worker.fetch(post(job()), env);
    expect(first.status).toBe(202);
    expect(second.status).toBe(202);
    const a = (await first.json()) as { run_id: string; status: string };
    const b = (await second.json()) as { run_id: string; status: string };
    expect(a.run_id).toBe(b.run_id);
    expect(b.status).toBe("duplicate");
    expect(starts).toEqual([a.run_id]);
  });

  it("returns already_running for the same concurrency without a second start", async () => {
    const { session, starts } = harness();
    const env = envFor(session);
    const first = await worker.fetch(post(job()), env);
    const second = await worker.fetch(
      post(
        job({
          job_id: "market-data-refresh-evening",
          idempotency_key: "market-data-refresh-evening:2",
          scheduled_time: 2,
          cron: "30 21 * * *",
        }),
      ),
      env,
    );
    expect((await first.json() as { status: string }).status).toBe("accepted");
    const body = (await second.json()) as { status: string };
    expect(second.status).toBe(202);
    expect(body.status).toBe("already_running");
    expect(starts).toHaveLength(1);
  });
});

describe("heartbeat", () => {
  it("clears the lock on success and does not reschedule", async () => {
    const { session, alarms, statuses, starts } = harness();
    const accepted = await session.accept(job());
    alarms.length = 0;
    const remote = statuses.get(starts[0]);
    if (!remote) throw new Error("missing status");
    remote.status = "succeeded";
    remote.exit_code = 0;
    remote.finished_at = "2026-09-29T13:10:00.000Z";
    await session.alarm();
    expect(alarms).toEqual([]);
    expect((await session.health()).running).toEqual([]);
    expect(accepted.status).toBe("accepted");
  });

  it("reschedules about 60s out while the job is running", async () => {
    const { session, alarms } = harness();
    await session.accept(job({ idempotency_key: "market-data-refresh-morning:9" }));
    alarms.length = 0;
    await session.alarm();
    expect(alarms).toEqual([HEARTBEAT_MS]);
    expect((await session.health()).running).toHaveLength(1);
  });
});

describe("data plane env", () => {
  it("does not forward the runner auth token", () => {
    const keys = Object.keys(
      dataPlaneEnv({
        RUNNER_AUTH_TOKEN: "nope",
        RUNNER_CONTAINER: {} as DurableObjectNamespace,
      }),
    );
    expect(keys).not.toContain("RUNNER_AUTH_TOKEN");
    expect(keys).not.toContain("GH_ISSUE_TOKEN");
    expect(keys).toContain("FRED_API_KEY");
  });
});

describe("GET /v1/jobs/:id status refresh", () => {
  it("applies container status on GET while the lock is held", async () => {
    const { session, starts, statuses } = harness();
    const accepted = await session.accept(
      job({ idempotency_key: "market-data-refresh-morning:get-refresh" }),
    );
    const remote = statuses.get(starts[0]);
    if (!remote) throw new Error("missing status");
    remote.log_tail = "hello from container";
    remote.git_sha = "deadbeef";
    remote.started_at = "2026-09-29T13:00:01.123456+00:00";
    const res = await session.fetch(
      new Request(`https://digiquant-runner/v1/jobs/${accepted.run_id}`),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      log_tail: string;
      git_sha: string;
      started_at: string;
      status: string;
    };
    expect(body.status).toBe("running");
    expect(body.log_tail).toBe("hello from container");
    expect(body.git_sha).toBe("deadbeef");
    expect(body.started_at).toBe("2026-09-29T13:00:01.123456+00:00");
  });
});
