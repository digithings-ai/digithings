/**
 * Durable Object job ledger for digiquant-runner (issue #4761).
 * Idempotency, concurrency locks, and the 60s heartbeat live here so tests
 * can drive them without starting a Container.
 */
import commandsJson from "../commands.json";
import { assertKnownCommand, loadCommands, type CommandSpec } from "./commands";

export const HEARTBEAT_MS = 60_000;
export const MAX_INFLIGHT = 2;
const WATCHDOG_GRACE_SECONDS = 120;
const STATE_KEY = "runner-state";

export const COMMANDS: Record<string, CommandSpec> = loadCommands(commandsJson);

export type RunStatus = "accepted" | "running" | "succeeded" | "failed" | "timed_out";

export type AcceptStatus = "accepted" | "already_running" | "duplicate";

export type RunJobRequest = {
  job_id: string;
  command: string;
  args: Record<string, string>;
  concurrency: string;
  timeout_seconds: number;
  code_ref: "main";
  cron: string;
  scheduled_time: number;
  idempotency_key: string;
};

export type RunJobResponse = {
  ok: true;
  run_id: string;
  status: AcceptStatus;
};

export type RunRecord = {
  run_id: string;
  job_id: string;
  command: string;
  args: Record<string, string>;
  concurrency: string;
  timeout_seconds: number;
  idempotency_key: string;
  status: RunStatus;
  exit_code: number | null;
  started_at: string | null;
  finished_at: string | null;
  git_sha: string;
  log_tail: string;
  started_at_ms: number;
};

export type ContainerStatus = {
  status: RunStatus;
  exit_code: number | null;
  started_at: string | null;
  finished_at: string | null;
  git_sha: string;
  log_tail: string;
  reason?: string | null;
};

export type ContainerPort = {
  startRun(body: {
    run_id: string;
    command: string;
    args: Record<string, string>;
    timeout_seconds: number;
  }): Promise<void>;
  readStatus(runId: string): Promise<ContainerStatus | null>;
};

export type RunnerKv = {
  get<T>(key: string): Promise<T | undefined>;
  put(key: string, value: unknown): Promise<void>;
  delete(key: string): Promise<boolean | void>;
};

type LockRecord = {
  run_id: string;
  concurrency: string;
  started_at_ms: number;
  timeout_seconds: number;
};

type Ledger = {
  idem: Record<string, string>;
  locks: Record<string, LockRecord>;
  runs: Record<string, RunRecord>;
  queue: string[];
};

export type SessionDeps = {
  kv: RunnerKv;
  port: ContainerPort;
  /** May be sync or async; callers always await. */
  scheduleAlarm: (delayMs: number) => void | Promise<void>;
  now?: () => number;
};

function emptyLedger(): Ledger {
  return { idem: {}, locks: {}, runs: {}, queue: [] };
}

function isTerminal(status: RunStatus): boolean {
  return status === "succeeded" || status === "failed" || status === "timed_out";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

export function parseRunJob(value: unknown): RunJobRequest | null {
  const body = asRecord(value);
  if (!body) return null;
  const args = asRecord(body.args) ?? {};
  const stringArgs: Record<string, string> = {};
  for (const [key, item] of Object.entries(args)) {
    if (typeof item !== "string") return null;
    stringArgs[key] = item;
  }
  if (typeof body.job_id !== "string" || typeof body.command !== "string") return null;
  if (typeof body.concurrency !== "string" || typeof body.idempotency_key !== "string") {
    return null;
  }
  if (typeof body.timeout_seconds !== "number" || typeof body.scheduled_time !== "number") {
    return null;
  }
  if (body.code_ref !== "main" || typeof body.cron !== "string") return null;
  if (!body.idempotency_key) return null;
  return {
    job_id: body.job_id,
    command: body.command,
    args: stringArgs,
    concurrency: body.concurrency,
    timeout_seconds: body.timeout_seconds,
    code_ref: "main",
    cron: body.cron,
    scheduled_time: body.scheduled_time,
    idempotency_key: body.idempotency_key,
  };
}

export class RunnerSession {
  private readonly now: () => number;

  constructor(private readonly deps: SessionDeps) {
    this.now = deps.now ?? (() => Date.now());
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/$/, "") || "/";
    if (request.method === "GET" && path === "/healthz") {
      return Response.json(await this.health());
    }
    if (request.method === "POST" && path === "/v1/jobs") {
      let parsed: unknown;
      try {
        parsed = await request.json();
      } catch {
        return Response.json({ error: "invalid_json" }, { status: 400 });
      }
      const job = parseRunJob(parsed);
      if (!job) return Response.json({ error: "invalid_body" }, { status: 400 });
      try {
        assertKnownCommand(job.command, COMMANDS);
      } catch (err) {
        const message = err instanceof Error ? err.message : "unknown command";
        return Response.json({ error: message }, { status: 400 });
      }
      try {
        const body = await this.accept(job);
        return Response.json(body, { status: 202 });
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        return Response.json({ error: message }, { status: 500 });
      }
    }
    if (request.method === "GET" && path.startsWith("/v1/jobs/")) {
      const runId = decodeURIComponent(path.slice("/v1/jobs/".length));
      const run = await this.getRun(runId);
      if (!run) return Response.json({ error: "not_found" }, { status: 404 });
      return Response.json(publicRun(run));
    }
    return new Response("Not Found", { status: 404 });
  }

  async health(): Promise<{
    ok: true;
    service: "digiquant-runner";
    git_sha: string;
    running: string[];
  }> {
    const ledger = await this.load();
    const running = Object.values(ledger.locks).map((lock) => lock.run_id);
    const sha =
      Object.values(ledger.runs)
        .map((run) => run.git_sha)
        .find((value) => value && value !== "unknown") ?? "unknown";
    return { ok: true, service: "digiquant-runner", git_sha: sha, running };
  }

  async hasActiveWork(): Promise<boolean> {
    const ledger = await this.load();
    return Object.keys(ledger.locks).length > 0 || ledger.queue.length > 0;
  }

  async accept(request: RunJobRequest): Promise<RunJobResponse> {
    const ledger = await this.load();
    const existingId = ledger.idem[request.idempotency_key];
    if (existingId) {
      return { ok: true, run_id: existingId, status: "duplicate" };
    }
    const held = ledger.locks[request.concurrency];
    if (held) {
      return { ok: true, run_id: held.run_id, status: "already_running" };
    }
    if (ledger.queue.some((id) => ledger.runs[id]?.concurrency === request.concurrency)) {
      const queued = ledger.queue.find(
        (id) => ledger.runs[id]?.concurrency === request.concurrency,
      );
      return {
        ok: true,
        run_id: queued ?? request.idempotency_key,
        status: "already_running",
      };
    }
    const run = this.freshRun(request);
    ledger.idem[request.idempotency_key] = run.run_id;
    ledger.runs[run.run_id] = run;
    const inflight = Object.keys(ledger.locks).length;
    if (inflight >= MAX_INFLIGHT) {
      ledger.queue.push(run.run_id);
      await this.save(ledger);
      await Promise.resolve(this.deps.scheduleAlarm(HEARTBEAT_MS));
      return { ok: true, run_id: run.run_id, status: "accepted" };
    }
    this.holdLock(ledger, run);
    await this.save(ledger);
    try {
      await this.deps.port.startRun({
        run_id: run.run_id,
        command: run.command,
        args: run.args,
        timeout_seconds: run.timeout_seconds,
      });
    } catch (err) {
      await this.rollback(run.run_id);
      throw err;
    }
    // Seed ledger from container immediately so GET /v1/jobs/:id has
    // started_at/log_tail before the first heartbeat.
    try {
      const remote = await this.deps.port.readStatus(run.run_id);
      if (remote) {
        this.applyRemote(run, remote);
        await this.save(ledger);
      }
    } catch {
      // Heartbeat / GET poll will retry.
    }
    await Promise.resolve(this.deps.scheduleAlarm(HEARTBEAT_MS));
    return { ok: true, run_id: run.run_id, status: "accepted" };
  }

  async alarm(): Promise<void> {
    const ledger = await this.load();
    let reschedule = false;
    for (const group of Object.keys(ledger.locks)) {
      const keep = await this.pollLock(ledger, group);
      if (keep) reschedule = true;
    }
    reschedule = (await this.promote(ledger)) || reschedule;
    await this.save(ledger);
    if (reschedule || ledger.queue.length > 0 || Object.keys(ledger.locks).length > 0) {
      await Promise.resolve(this.deps.scheduleAlarm(HEARTBEAT_MS));
    }
  }

  async getRun(runId: string): Promise<RunRecord | null> {
    const ledger = await this.load();
    const run = ledger.runs[runId];
    if (!run) return null;
    // Operator GET must not wait for the 60s heartbeat. Refresh from the
    // container while this run still holds its concurrency lock (#4761 Kick2
    // timed out with empty log_tail because ledger was never applyRemote'd).
    const lock = Object.values(ledger.locks).find((item) => item.run_id === runId);
    if (lock) {
      await this.pollLock(ledger, lock.concurrency);
      await this.save(ledger);
      return ledger.runs[runId] ?? run;
    }
    return run;
  }

  private freshRun(request: RunJobRequest): RunRecord {
    const now = this.now();
    return {
      run_id: crypto.randomUUID(),
      job_id: request.job_id,
      command: request.command,
      args: request.args,
      concurrency: request.concurrency,
      timeout_seconds: request.timeout_seconds,
      idempotency_key: request.idempotency_key,
      status: "accepted",
      exit_code: null,
      started_at: new Date(now).toISOString(),
      finished_at: null,
      git_sha: "unknown",
      log_tail: "",
      started_at_ms: now,
    };
  }

  private holdLock(ledger: Ledger, run: RunRecord): void {
    ledger.locks[run.concurrency] = {
      run_id: run.run_id,
      concurrency: run.concurrency,
      started_at_ms: run.started_at_ms,
      timeout_seconds: run.timeout_seconds,
    };
    run.status = "running";
  }

  private async pollLock(ledger: Ledger, group: string): Promise<boolean> {
    const lock = ledger.locks[group];
    if (!lock) return false;
    const run = ledger.runs[lock.run_id];
    if (!run) {
      delete ledger.locks[group];
      return false;
    }
    let remote: ContainerStatus | null = null;
    try {
      remote = await this.deps.port.readStatus(lock.run_id);
    } catch {
      remote = null;
    }
    const ageSeconds = (this.now() - lock.started_at_ms) / 1000;
    const pastDeadline = ageSeconds > lock.timeout_seconds + WATCHDOG_GRACE_SECONDS;
    if (remote) this.applyRemote(run, remote);
    if (pastDeadline && !isTerminal(run.status)) {
      run.status = "timed_out";
      run.exit_code = 124;
      run.finished_at = new Date(this.now()).toISOString();
      delete ledger.locks[group];
      return false;
    }
    if (!remote) return true;
    if (isTerminal(run.status)) {
      delete ledger.locks[group];
      return false;
    }
    return true;
  }

  private applyRemote(run: RunRecord, remote: ContainerStatus): void {
    run.status = remote.status;
    run.exit_code = remote.exit_code;
    run.log_tail = remote.log_tail ?? "";
    if (remote.git_sha) run.git_sha = remote.git_sha;
    if (remote.started_at) run.started_at = remote.started_at;
    if (remote.finished_at) run.finished_at = remote.finished_at;
  }

  private async promote(ledger: Ledger): Promise<boolean> {
    let started = false;
    const waiting = [...ledger.queue];
    ledger.queue = [];
    for (const runId of waiting) {
      const run = ledger.runs[runId];
      if (!run) continue;
      if (Object.keys(ledger.locks).length >= MAX_INFLIGHT || ledger.locks[run.concurrency]) {
        ledger.queue.push(runId);
        continue;
      }
      this.holdLock(ledger, run);
      try {
        await this.deps.port.startRun({
          run_id: run.run_id,
          command: run.command,
          args: run.args,
          timeout_seconds: run.timeout_seconds,
        });
        started = true;
      } catch {
        delete ledger.locks[run.concurrency];
        run.status = "failed";
        run.finished_at = new Date(this.now()).toISOString();
      }
    }
    return started;
  }

  private async rollback(runId: string): Promise<void> {
    const ledger = await this.load();
    const run = ledger.runs[runId];
    if (!run) return;
    delete ledger.locks[run.concurrency];
    delete ledger.runs[runId];
    delete ledger.idem[run.idempotency_key];
    ledger.queue = ledger.queue.filter((id) => id !== runId);
    await this.save(ledger);
  }

  private async load(): Promise<Ledger> {
    const stored = await this.deps.kv.get<Ledger>(STATE_KEY);
    if (!stored) return emptyLedger();
    return {
      idem: stored.idem ?? {},
      locks: stored.locks ?? {},
      runs: stored.runs ?? {},
      queue: stored.queue ?? [],
    };
  }

  private async save(ledger: Ledger): Promise<void> {
    await this.deps.kv.put(STATE_KEY, ledger);
  }
}

function publicRun(run: RunRecord): {
  run_id: string;
  job_id: string;
  status: RunStatus;
  exit_code: number | null;
  started_at: string | null;
  finished_at: string | null;
  git_sha: string;
  log_tail: string;
} {
  return {
    run_id: run.run_id,
    job_id: run.job_id,
    status: run.status,
    exit_code: run.exit_code,
    started_at: run.started_at,
    finished_at: run.finished_at,
    git_sha: run.git_sha,
    log_tail: run.log_tail,
  };
}

export function memoryKv(): RunnerKv {
  const data = new Map<string, unknown>();
  return {
    async get<T>(key: string): Promise<T | undefined> {
      return data.get(key) as T | undefined;
    },
    async put(key: string, value: unknown): Promise<void> {
      data.set(key, structuredClone(value));
    },
    async delete(key: string): Promise<boolean> {
      return data.delete(key);
    },
  };
}
