/**
 * digiquant-runner Durable Object container (issue #4761).
 * One pinned instance (`runner-v1`). Idle sleep is 2m; a held lock extends it
 * to 30m and the heartbeat fetches /status every 60s so the platform does not
 * reap a running job.
 */
import { Container } from "@cloudflare/containers";
import { dataPlaneEnv, type Env } from "./env";
import { RunnerSession, type ContainerPort, type RunnerKv } from "./runner-session";

export const RUNNER_CONTAINER_ID = "runner-v1";

export class DigiQuantRunnerContainer extends Container<Env> {
  defaultPort = 8080;
  requiredPorts = [8080];
  /** Idle tail. Raised to 30m while a lock is held. */
  sleepAfter = "2m";
  enableInternet = true;

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
    this.sleepAfter = (await session.hasActiveWork()) ? "30m" : "2m";
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
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(`container /status HTTP ${res.status}`);
      return res.json();
    },
  };
}
