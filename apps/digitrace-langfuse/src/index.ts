/**
 * digitrace Langfuse — Worker fronting Langfuse Web (+ keep-warm Worker Container).
 *
 * Phase 1 (#4930): self-hosted Langfuse on Cloudflare Containers.
 * Public traffic → Langfuse Web (:3000). Langfuse Worker (:3030) is not
 * publicly routed; the edge wakes it on /_langfuse/worker-wake so queue
 * processing survives Container sleep-after-idle.
 *
 * Hostname (HUMAN GATE): trace.digithings.ai — enable route in wrangler.toml
 * only after Platform DNS + secrets are ready.
 */
import { Container, getContainer } from "@cloudflare/containers";
import { env as workerEnvBinding } from "cloudflare:workers";
import {
  LANGFUSE_WEB_CONTAINER_ID,
  LANGFUSE_WORKER_CONTAINER_ID,
} from "./paths";

export {
  isEdgeOnlyPath,
  LANGFUSE_WEB_CONTAINER_ID,
  LANGFUSE_WORKER_CONTAINER_ID,
} from "./paths";

/** Wrangler injects vars/secrets; cast until `wrangler types` is generated. */
const workerVars = workerEnvBinding as unknown as Env;

/**
 * Env forwarded into both Langfuse Containers. Secrets come from
 * `wrangler secret put`; plain vars from wrangler.toml `[vars]`.
 * A secret that is `put` but missing here never reaches the process.
 */
function langfuseEnvVars(): Record<string, string> {
  return {
    DATABASE_URL: workerVars.DATABASE_URL ?? "",
    NEXTAUTH_SECRET: workerVars.NEXTAUTH_SECRET ?? "",
    NEXTAUTH_URL: workerVars.NEXTAUTH_URL ?? "",
    SALT: workerVars.SALT ?? "",
    ENCRYPTION_KEY: workerVars.ENCRYPTION_KEY ?? "",
    CLICKHOUSE_URL: workerVars.CLICKHOUSE_URL ?? "",
    CLICKHOUSE_MIGRATION_URL: workerVars.CLICKHOUSE_MIGRATION_URL ?? "",
    CLICKHOUSE_USER: workerVars.CLICKHOUSE_USER ?? "",
    CLICKHOUSE_PASSWORD: workerVars.CLICKHOUSE_PASSWORD ?? "",
    CLICKHOUSE_DB: workerVars.CLICKHOUSE_DB ?? "default",
    CLICKHOUSE_CLUSTER_ENABLED: workerVars.CLICKHOUSE_CLUSTER_ENABLED ?? "false",
    REDIS_CONNECTION_STRING: workerVars.REDIS_CONNECTION_STRING ?? "",
    REDIS_HOST: workerVars.REDIS_HOST ?? "",
    REDIS_PORT: workerVars.REDIS_PORT ?? "",
    REDIS_AUTH: workerVars.REDIS_AUTH ?? "",
    LANGFUSE_S3_EVENT_UPLOAD_BUCKET:
      workerVars.LANGFUSE_S3_EVENT_UPLOAD_BUCKET ?? "digitrace-langfuse-events",
    LANGFUSE_S3_EVENT_UPLOAD_REGION:
      workerVars.LANGFUSE_S3_EVENT_UPLOAD_REGION ?? "auto",
    LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT:
      workerVars.LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT ?? "",
    LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID:
      workerVars.LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID ?? "",
    LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY:
      workerVars.LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY ?? "",
    LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE:
      workerVars.LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE ?? "true",
    LANGFUSE_S3_EVENT_UPLOAD_PREFIX:
      workerVars.LANGFUSE_S3_EVENT_UPLOAD_PREFIX ?? "events/",
  };
}

export class LangfuseWebContainer extends Container {
  defaultPort = 3000;
  /** Short idle tail: each wake bills for the whole sleepAfter window. */
  sleepAfter = "5m";
  envVars = langfuseEnvVars();
}

export class LangfuseWorkerContainer extends Container {
  defaultPort = 3030;
  /**
   * Queue drain has no steady public HTTP. Keep a long sleepAfter so a wake
   * (deploy /_langfuse/worker-wake) stays warm; do not rely on CH-in-container.
   */
  sleepAfter = "7d";
  envVars = langfuseEnvVars();
}

export interface Env {
  LANGFUSE_WEB: DurableObjectNamespace<LangfuseWebContainer>;
  LANGFUSE_WORKER: DurableObjectNamespace<LangfuseWorkerContainer>;
  /** Optional R2 binding — uploads use S3 env inside Containers, not this API. */
  LANGFUSE_EVENTS?: R2Bucket;
  DATABASE_URL?: string;
  NEXTAUTH_SECRET?: string;
  NEXTAUTH_URL?: string;
  SALT?: string;
  ENCRYPTION_KEY?: string;
  CLICKHOUSE_URL?: string;
  CLICKHOUSE_MIGRATION_URL?: string;
  CLICKHOUSE_USER?: string;
  CLICKHOUSE_PASSWORD?: string;
  CLICKHOUSE_DB?: string;
  CLICKHOUSE_CLUSTER_ENABLED?: string;
  REDIS_CONNECTION_STRING?: string;
  REDIS_HOST?: string;
  REDIS_PORT?: string;
  REDIS_AUTH?: string;
  LANGFUSE_S3_EVENT_UPLOAD_BUCKET?: string;
  LANGFUSE_S3_EVENT_UPLOAD_REGION?: string;
  LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT?: string;
  LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID?: string;
  LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY?: string;
  LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE?: string;
  LANGFUSE_S3_EVENT_UPLOAD_PREFIX?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/_langfuse/healthz") {
      return Response.json({
        ok: true,
        service: "digitrace-langfuse",
        phase: 1,
      });
    }

    if (url.pathname === "/_langfuse/worker-wake") {
      // Touch the Worker Container so queue processing stays warm after idle.
      const worker = getContainer(
        env.LANGFUSE_WORKER,
        LANGFUSE_WORKER_CONTAINER_ID,
      );
      try {
        await worker.fetch(
          new Request("http://langfuse-worker/api/health", { method: "GET" }),
        );
      } catch {
        // Container may still be booting; wake request is best-effort.
      }
      return Response.json({ ok: true, woken: "langfuse-worker" });
    }

    const web = getContainer(env.LANGFUSE_WEB, LANGFUSE_WEB_CONTAINER_ID);
    return web.fetch(request);
  },
};
