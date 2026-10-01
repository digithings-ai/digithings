import { describe, expect, it } from "vitest";
import worker from "./index";
import { dataPlaneEnv, type Env, type HouseLedger } from "./env";
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

type Started = {
  run_id: string;
  command: string;
  args: Record<string, string>;
};

type HarnessOptions = {
  now?: () => number;
  startRun?: ContainerPort["startRun"];
  readStatus?: ContainerPort["readStatus"];
  archive?: HouseLedger;
};

function harness(opts: HarnessOptions = {}): {
  session: RunnerSession;
  starts: string[];
  bodies: Started[];
  alarms: number[];
  statuses: Map<string, ContainerStatus>;
  clock: { ms: number };
} {
  const starts: string[] = [];
  const bodies: Started[] = [];
  const alarms: number[] = [];
  const statuses = new Map<string, ContainerStatus>();
  const clock = { ms: T0 };
  const port: ContainerPort = {
    startRun:
      opts.startRun ??
      (async (body) => {
        starts.push(body.run_id);
        bodies.push({ run_id: body.run_id, command: body.command, args: body.args });
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
    archive: opts.archive,
  });
  return { session, starts, bodies, alarms, statuses, clock };
}

function memoryArchive(seed: Record<string, string> = {}): HouseLedger & {
  data: Map<string, string>;
} {
  const data = new Map(Object.entries(seed));
  return {
    data,
    async head(key: string) {
      return data.has(key) ? { key } : null;
    },
    async get(key: string) {
      const text = data.get(key);
      if (text === undefined) return null;
      return { text: async () => text };
    },
    async put(key: string, body: string) {
      data.set(key, body);
      return { key };
    },
  };
}

function envFor(
  session: RunnerSession,
  opts: { archive?: Record<string, string> | null } = {},
): Env {
  const env: Env = {
    RUNNER_AUTH_TOKEN: "test-token",
    RUNNER_CONTAINER: {
      idFromName: (name: string) => name,
      get: () => ({ fetch: (request: Request) => session.fetch(request) }),
    } as unknown as DurableObjectNamespace,
  };
  if (opts.archive !== null) {
    env.ARCHIVE = memoryArchive(opts.archive ?? {});
  }
  return env;
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
      post(job({ command: "not-a-command", concurrency: "digiquant-pipeline" })),
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

  it("ignores a missing ledger for commands other than house-run", async () => {
    const { session, starts } = harness();
    const res = await worker.fetch(post(job()), envFor(session, { archive: null }));
    expect(res.status).toBe(202);
    expect(starts).toHaveLength(1);
  });

  it("skips house-run before start when today's success object exists", async () => {
    const { session, starts } = harness();
    const env = envFor(session, {
      archive: { "pipeline-runs/house-run/2026-09-30/success.json": "{\"run_id\":\"old\"}" },
    });
    const res = await worker.fetch(
      post(job({
        command: "house-run",
        concurrency: "digiquant-pipeline",
        args: { refresh_scope: "none", run_date: "2026-09-30" },
      })),
      env,
    );
    expect(res.status).toBe(202);
    expect(await res.json()).toMatchObject({ status: "skipped", run_id: "old" });
    expect(starts).toHaveLength(0);
  });

  it("force bypasses the success object and starts", async () => {
    const { session, starts } = harness();
    const env = envFor(session, {
      archive: {
        "pipeline-runs/house-run/2026-09-30/success.json": "{\"run_id\":\"old\"}",
      },
    });
    const res = await worker.fetch(
      post(job({
        command: "house-run",
        concurrency: "digiquant-pipeline",
        args: { refresh_scope: "none", run_date: "2026-09-30", force: "true" },
        idempotency_key: "house-run-09:force",
      })),
      env,
    );
    expect(res.status).toBe(202);
    expect((await res.json() as { status: string }).status).toBe("accepted");
    expect(starts).toHaveLength(1);
  });

  it("refuses house-run when the ledger binding is missing", async () => {
    const { session, starts } = harness();
    const res = await worker.fetch(
      post(job({
        command: "house-run",
        concurrency: "digiquant-pipeline",
        args: { refresh_scope: "none", run_date: "2026-09-30" },
        idempotency_key: "house-run-09:no-ledger",
      })),
      envFor(session, { archive: null }),
    );
    expect(res.status).toBe(500);
    expect(await res.json()).toMatchObject({ error: "house_ledger_unconfigured" });
    expect(starts).toHaveLength(0);
  });

  it("queues prices while house-run is locked", async () => {
    const { session, starts } = harness();
    const env = envFor(session);
    const house = await worker.fetch(
      post(job({
        command: "house-run",
        job_id: "house-run-09",
        concurrency: "digiquant-pipeline",
        timeout_seconds: 14400,
        idempotency_key: "house-run-09:1",
        args: { refresh_scope: "none", run_date: "2026-09-30" },
      })),
      env,
    );
    expect(house.status).toBe(202);
    const prices = await worker.fetch(
      post(job({
        command: "market-data-refresh",
        concurrency: "market-data-refresh",
        idempotency_key: "market-data-refresh-morning:2",
      })),
      env,
    );
    expect(prices.status).toBe(202);
    expect((await prices.json() as { status: string }).status).toBe("accepted");
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
    expect(keys).not.toContain("FRED_API_KEY");
    // House keys are on the container. allocation-shadow's allowlist still drops them.
    expect([...keys].sort()).toEqual(
      [
        "CHEAPERINFERENCE_API_BASE",
        "CHEAPERINFERENCE_API_KEY",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_EMAIL_API_TOKEN",
        "CORE_POSTGRES_URI",
        "CORE_SUPABASE_SERVICE_KEY",
        "CORE_SUPABASE_URL",
        "DIGIQUANT_DIGIKEY_API_KEY",
        "DIGIQUANT_RUNNER_GIT_SHA",
        "LANGSMITH_API_KEY",
        "NOTIFY_FROM",
        "OPENROUTER_API_KEY",
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
  it("marks timed_out with exit 124 when unreachable past timeout + grace", async () => {
    const timeoutSeconds = 10;
    const { session, clock, alarms, statuses, starts } = harness();
    const accepted = await session.accept(
      job({
        idempotency_key: "market-data-refresh-morning:watchdog",
        timeout_seconds: timeoutSeconds,
      }),
    );
    // Unreachable container: ledger may clear a zombie lock. A still-running
    // remote must NOT be timed out here (see next test).
    statuses.delete(starts[0]);
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

  it("keeps the lock while the container still reports running past deadline", async () => {
    const timeoutSeconds = 10;
    const { session, clock, alarms, starts, statuses } = harness();
    await session.accept(
      job({
        idempotency_key: "market-data-refresh-morning:watchdog-alive",
        timeout_seconds: timeoutSeconds,
      }),
    );
    const remote = statuses.get(starts[0]);
    if (!remote) throw new Error("missing status");
    // Simulate cold-boot: container started mid-way through the accept clock.
    remote.started_at = new Date(T0 + 5 * 60 * 1000).toISOString();
    alarms.length = 0;
    clock.ms = T0 + (timeoutSeconds + WATCHDOG_GRACE_SECONDS + 1) * 1000;
    await session.alarm();
    expect((await session.health()).running).toEqual([starts[0]]);
    expect(alarms).toEqual([HEARTBEAT_MS]);
    // After aligning to remote.started_at, the budget still has room.
    clock.ms =
      Date.parse(remote.started_at) + (timeoutSeconds + WATCHDOG_GRACE_SECONDS + 1) * 1000;
    // Still running remotely — keep the lock even past the aligned deadline.
    await session.alarm();
    expect((await session.health()).running).toEqual([starts[0]]);
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

  it("writes success.json and starts allocation-shadow after house-run succeeds", async () => {
    const archive = memoryArchive();
    const { session, starts, statuses, bodies } = harness({ archive });
    const accepted = await session.accept(
      job({
        command: "house-run",
        job_id: "house-run-09",
        concurrency: "digiquant-pipeline",
        timeout_seconds: 14400,
        idempotency_key: "house-run-09:success",
        args: { refresh_scope: "none", run_date: "2026-09-30" },
      }),
    );
    const remote = statuses.get(starts[0]);
    if (!remote) throw new Error("missing status");
    remote.status = "succeeded";
    remote.exit_code = 0;
    remote.finished_at = "2026-09-30T17:00:00.000Z";
    await session.alarm();
    const raw = archive.data.get("pipeline-runs/house-run/2026-09-30/success.json");
    expect(raw).toBeTruthy();
    const saved = JSON.parse(raw ?? "{}") as {
      run_id: string;
      git_sha: string;
      finished_at: string;
    };
    expect(saved).toEqual({
      run_id: accepted.run_id,
      git_sha: "abc123",
      finished_at: "2026-09-30T17:00:00.000Z",
    });
    const shadow = bodies.find((body) => body.command === "allocation-shadow");
    expect(shadow?.args.artifact_prefix).toBe(`pipeline-runs/house-run/${accepted.run_id}/`);
    expect(shadow?.args.source_branch).toBe("main");
    expect((await session.health()).running).toEqual([shadow?.run_id]);
  });

  it("starts a queued price tick only after the house-run lock clears", async () => {
    const { session, starts, statuses, bodies } = harness();
    const house = await session.accept(
      job({
        command: "house-run",
        job_id: "house-run-09",
        concurrency: "digiquant-pipeline",
        timeout_seconds: 14400,
        idempotency_key: "house-run-09:queue",
        args: { refresh_scope: "none", run_date: "2026-09-30" },
      }),
    );
    const prices = await session.accept(
      job({
        command: "market-data-refresh",
        concurrency: "market-data-refresh",
        idempotency_key: "market-data-refresh-morning:queued",
        scheduled_time: 2,
      }),
    );
    expect(prices.status).toBe("accepted");
    expect(starts).toEqual([house.run_id]);
    const remote = statuses.get(house.run_id);
    if (!remote) throw new Error("missing status");
    remote.status = "succeeded";
    remote.exit_code = 0;
    remote.finished_at = "2026-09-30T17:00:00.000Z";
    await session.alarm();
    expect(bodies.map((body) => body.command)).toEqual([
      "house-run",
      "market-data-refresh",
      "allocation-shadow",
    ]);
  });

  it("does not start house-run beside a live price tick", async () => {
    const { session, starts } = harness();
    const prices = await session.accept(job({ idempotency_key: "prices:hold" }));
    const house = await session.accept(
      job({
        command: "house-run",
        concurrency: "digiquant-pipeline",
        timeout_seconds: 14400,
        idempotency_key: "house-run-09:behind",
        args: { refresh_scope: "none", run_date: "2026-09-30" },
      }),
    );
    expect(house.status).toBe("accepted");
    expect(starts).toEqual([prices.run_id]);
  });
});
