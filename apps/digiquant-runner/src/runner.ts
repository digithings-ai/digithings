/**
 * digiquant-runner Durable Object container (issue #4761).
 * One pinned instance (`runner-v1`). Idle sleep is 2m; a held lock extends it
 * to 30m and the heartbeat fetches /status every 60s so the platform does not
 * reap a running job.
 */
import { Container } from "@cloudflare/containers";
import { dataPlaneEnv, type Env } from "./env";
import {
  HEARTBEAT_MS,
  RunLostError,
  RunnerSession,
  type ContainerPort,
  type RunnerKv,
} from "./runner-session";

export const RUNNER_CONTAINER_ID = "runner-v1";

/**
 * Re-arm the heartbeat after a Durable Object reset (DIG-3061).
 *
 * A reset (a code update, or eviction) drops the heartbeat alarm, and nothing
 * re-armed it, so an in-flight house run kept its lock forever and no
 * success.json was ever written.
 *
 * An already-armed alarm means this is the ordinary instantiation - a request,
 * or the alarm's own wake - not a reset. Container.schedule INSERTs a fresh row
 * on every call, so scheduling again would double the poll rate for the life of
 * the instance. Returns true when a heartbeat was scheduled.
 */
export async function rearmHeartbeatAfterReset(deps: {
  getAlarm: () => Promise<number | null>;
  hasActiveWork: () => Promise<boolean>;
  scheduleHeartbeat: () => Promise<void>;
}): Promise<boolean> {
  if ((await deps.getAlarm()) !== null) return false;
  if (!(await deps.hasActiveWork())) return false;
  await deps.scheduleHeartbeat();
  return true;
}

export class DigiQuantRunnerContainer extends Container<Env> {
  defaultPort = 8080;
  requiredPorts = [8080];
  /** Idle tail. Raised to 30m while a lock is held. */
  sleepAfter = "1m";
  enableInternet = true;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    // Deferred until the instance is idle so the re-arm never races a request,
    // and swallowed on failure: a missed re-arm must not take the instance down.
    this.ctx
      .blockConcurrencyWhile(() =>
        rearmHeartbeatAfterReset({
          getAlarm: () => this.ctx.storage.getAlarm(),
          hasActiveWork: () => this.session().hasActiveWork(),
          scheduleHeartbeat: () => this.schedule(HEARTBEAT_MS / 1000, "heartbeat").then(() => undefined),
        }),
      )
      .catch(() => undefined);
  }

  override async fetch(request: Request): Promise<Response> {
    this.envVars = dataPlaneEnv(this.env);
    const session = this.session();
    const response = await session.fetch(request);
    await this.applyActivityWindow(session);
    return response;
  }

  /** Alarm callback. Container.schedule names this method. */
  async heartbeat(): Promise<void> {
    this.envVars = dataPlaneEnv(this.env);
    const session = this.session();
    await session.alarm();
    await this.applyActivityWindow(session);
  }

  override async onActivityExpired(): Promise<void> {
    if (await this.session().hasActiveWork()) {
      this.sleepAfter = "30m";
      this.renewActivityTimeout();
      return;
    }
    await super.onActivityExpired();
  }

  private session(): RunnerSession {
    return new RunnerSession({
      kv: kvFromStorage(this.ctx.storage),
      port: portFromContainer(this),
      archive: this.env.ARCHIVE,
      scheduleAlarm: (delayMs: number) => {
        const seconds = Math.max(1, Math.round(delayMs / 1000));
        // Must await: void-schedule can drop the DO alarm registration when the
        // request ends before INSERT/setAlarm completes (#4761 empty log_tail).
        return this.schedule(seconds, "heartbeat").then(() => undefined);
      },
    });
  }

  private async applyActivityWindow(session: RunnerSession): Promise<void> {
    this.sleepAfter = (await session.hasActiveWork()) ? "30m" : "1m";
    this.renewActivityTimeout();
  }
}

function kvFromStorage(storage: DurableObjectStorage): RunnerKv {
  return {
    get: (key) => storage.get(key),
    put: (key, value) => storage.put(key, value),
    delete: (key) => storage.delete(key),
  };
}

function portFromContainer(container: DigiQuantRunnerContainer): ContainerPort {
  return {
    async startRun(body) {
      const res = await container.containerFetch("http://container/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.status === 400) {
        throw new Error("unknown command");
      }
      if (res.status === 409) {
        throw new Error("container /run HTTP 409 already_running");
      }
      if (res.status !== 202 && !res.ok) {
        throw new Error(`container /run HTTP ${res.status}`);
      }
    },
    async readStatus(runId) {
      const res = await container.containerFetch(
        `http://container/status?run_id=${encodeURIComponent(runId)}`,
      );
      // A 404 is the container reporting it has no record of this run, which is
      // distinct from being unable to reach it: the registry lives in the
      // container's memory, so a container or DO restart really does lose the
      // run. Throwing the typed error lets pollLock separate "the run is gone"
      // from "the container is unreachable" (DIG-3061).
      if (res.status === 404) throw new RunLostError(runId);
      if (!res.ok) throw new Error(`container /status HTTP ${res.status}`);
      return res.json();
    },
  };
}
