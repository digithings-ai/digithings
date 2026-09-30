import { describe, expect, it } from "vitest";
import worker from "./index";
import { dataPlaneEnv, type Env } from "./env";
import {
  HEARTBEAT_MS,
  MAX_INFLIGHT,
  RunnerSession,
  WATCHDOG_GRACE_SECONDS,
  memoryKv,
  type ContainerPort,
  type ContainerStatus,
  type RunJobRequest,
} from "./runner-session";

const T0 = Date.parse("2026-09-29T13:00:00.000Z");

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

type HarnessOptions = {
  now?: () => number;
  startRun?: ContainerPort["startRun"];
  readStatus?: ContainerPort["readStatus"];
};

function harness(opts: HarnessOptions = {}): {
  session: RunnerSession;
  starts: string[];
  alarms: number[];
  statuses: Map<string, ContainerStatus>;
  clock: { ms: number };
} {
  const starts: string[] = [];
  const alarms: number[] = [];
  const statuses = new Map<string, ContainerStatus>();
  const clock = { ms: T0 };
  const port: ContainerPort = {
    startRun:
      opts.startRun ??
      (async (body) => {
        starts.push(body.run_id);
        statuses.set(body.run_id, {
          status: "running",
          exit_code: null,
          started_at: "2026-09-29T13:00:00.000+00:00",
          finished_at: null,
          git_sha: "abc123",
          log_tail: "boot",
        });
      }),
    readStatus:
      opts.readStatus ??
      (async (runId) => {
        return statuses.get(runId) ?? null;
      }),
  };
  const session = new RunnerSession({
    kv: memoryKv(),
    port,
    scheduleAlarm: async (delayMs) => {
      alarms.push(delayMs);
    },
    now: opts.now ?? (() => clock.ms),
  });
  return { session, starts, alarms, statuses, clock };
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
    // #4794: the macro panel needs no vendor key — pin the whitelist exactly.
    expect([...keys].sort()).toEqual(
      [
        "CORE_POSTGRES_URI",
        "CORE_SUPABASE_SERVICE_KEY",
        "CORE_SUPABASE_URL",
        "DIGIQUANT_RUNNER_GIT_SHA",
        "R2_ACCESS_KEY_ID",
        "R2_ACCOUNT_ID",
        "R2_BUCKET",
        "R2_SECRET_ACCESS_KEY",
      ].sort(),
    );
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

describe("accept seeds ledger from container (#4761 Kick2)", () => {
  it("persists container git_sha/started_at/log_tail before the first heartbeat", async () => {
    const { session } = harness();
    const accepted = await session.accept(
      job({ idempotency_key: "market-data-refresh-morning:seed" }),
    );
    const res = await session.fetch(
      new Request(`https://digiquant-runner/v1/jobs/${accepted.run_id}`),
    );
    const body = (await res.json()) as {
      git_sha: string;
      started_at: string;
      log_tail: string;
      status: string;
    };
    // Without seed, GET would still show DO defaults (git_sha=unknown, empty log).
    expect(body.status).toBe("running");
    expect(body.git_sha).toBe("abc123");
    expect(body.started_at).toBe("2026-09-29T13:00:00.000+00:00");
    expect(body.log_tail).toBe("boot");
  });

  it("still accepts when the post-start seed readStatus fails", async () => {
    let reads = 0;
    const { session, starts } = harness({
      readStatus: async () => {
        reads += 1;
        throw new Error("status unavailable");
      },
    });
    const accepted = await session.accept(
      job({ idempotency_key: "market-data-refresh-morning:seed-fail" }),
    );
    expect(accepted.status).toBe("accepted");
    expect(starts).toHaveLength(1);
    expect(reads).toBe(1);
    expect((await session.health()).running).toEqual([starts[0]]);
  });
});

describe("watchdog and poll resilience", () => {
  it("marks timed_out with exit 124 once past timeout + grace", async () => {
    const timeoutSeconds = 10;
    const { session, clock, alarms } = harness();
    const accepted = await session.accept(
      job({
        idempotency_key: "market-data-refresh-morning:watchdog",
        timeout_seconds: timeoutSeconds,
      }),
    );
    alarms.length = 0;
    clock.ms = T0 + (timeoutSeconds + WATCHDOG_GRACE_SECONDS + 1) * 1000;
    await session.alarm();
    const res = await session.fetch(
      new Request(`https://digiquant-runner/v1/jobs/${accepted.run_id}`),
    );
    const body = (await res.json()) as {
      status: string;
      exit_code: number | null;
      finished_at: string | null;
    };
    expect(body.status).toBe("timed_out");
    expect(body.exit_code).toBe(124);
    expect(body.finished_at).toBe(new Date(clock.ms).toISOString());
    expect((await session.health()).running).toEqual([]);
    expect(alarms).toEqual([]);
  });

  it("keeps the lock when readStatus throws during poll", async () => {
    let failReads = false;
    const { session, starts, alarms, statuses } = harness({
      readStatus: async (runId) => {
        if (failReads) throw new Error("container unreachable");
        return statuses.get(runId) ?? null;
      },
    });
    await session.accept(job({ idempotency_key: "market-data-refresh-morning:poll-fail" }));
    failReads = true;
    alarms.length = 0;
    await session.alarm();
    expect((await session.health()).running).toEqual([starts[0]]);
    expect(alarms).toEqual([HEARTBEAT_MS]);
  });

  it("rolls back lock and idempotency when startRun fails", async () => {
    let failStart = true;
    const { session, starts } = harness({
      startRun: async (body) => {
        if (failStart) throw new Error("container /run HTTP 500");
        starts.push(body.run_id);
      },
    });
    await expect(
      session.accept(job({ idempotency_key: "market-data-refresh-morning:start-fail" })),
    ).rejects.toThrow(/container \/run HTTP 500/);
    expect(starts).toHaveLength(0);
    expect((await session.health()).running).toEqual([]);

    failStart = false;
    const accepted = await session.accept(
      job({ idempotency_key: "market-data-refresh-morning:start-fail" }),
    );
    expect(accepted.status).toBe("accepted");
    expect(starts).toEqual([accepted.run_id]);
    expect((await session.health()).running).toEqual([accepted.run_id]);
  });

  it("queues when MAX_INFLIGHT locks are held and promotes after a free slot", async () => {
    const { session, starts, statuses, alarms } = harness();
    const first = await session.accept(
      job({
        concurrency: "group-a",
        idempotency_key: "a:1",
        job_id: "job-a",
      }),
    );
    const second = await session.accept(
      job({
        concurrency: "group-b",
        idempotency_key: "b:1",
        job_id: "job-b",
        cron: "0 14 * * *",
        scheduled_time: 2,
      }),
    );
    expect(starts).toHaveLength(MAX_INFLIGHT);
    const queued = await session.accept(
      job({
        concurrency: "group-c",
        idempotency_key: "c:1",
        job_id: "job-c",
        cron: "0 15 * * *",
        scheduled_time: 3,
      }),
    );
    expect(queued.status).toBe("accepted");
    expect(starts).toHaveLength(MAX_INFLIGHT);
    expect((await session.health()).running).toEqual(
      expect.arrayContaining([first.run_id, second.run_id]),
    );

    const remoteA = statuses.get(first.run_id);
    if (!remoteA) throw new Error("missing status");
    remoteA.status = "succeeded";
    remoteA.exit_code = 0;
    remoteA.finished_at = "2026-09-29T13:05:00.000Z";
    alarms.length = 0;
    await session.alarm();
    expect(starts).toHaveLength(MAX_INFLIGHT + 1);
    expect(starts[2]).toBe(queued.run_id);
    expect((await session.health()).running).toEqual(
      expect.arrayContaining([second.run_id, queued.run_id]),
    );
    expect(alarms).toEqual([HEARTBEAT_MS]);
  });
});
