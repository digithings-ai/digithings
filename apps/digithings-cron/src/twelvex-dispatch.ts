/**
 * Dispatch twelve-x ingest and heartbeat to the twelvex-runner Worker.
 * GITHUB_OVERRIDE_JOBS still sends the same job id to workflow_dispatch.
 * DRY_RUN=1 logs the route and does not call. The log line has no log tail
 * and no secret.
 */
import type { Env } from "./env";
import type { Job } from "./jobs";
import type { DispatchResult } from "./dispatch";

const TWELVEX_ORIGIN = "https://twelvex-runner";

type TwelveXAccept = {
  ok?: boolean;
  exit_code?: number;
  duration_ms?: number;
  alert?: string;
};

function logLine(fields: Record<string, unknown>): void {
  console.log(JSON.stringify(fields));
}

export async function dispatchTwelvex(
  env: Env,
  job: Job,
  cron: string,
): Promise<DispatchResult> {
  if (job.route !== "ingest" && job.route !== "heartbeat") {
    throw new Error(`job ${job.id}: twelvex requires route ingest or heartbeat`);
  }
  const bucket = job.inputs?.bucket;
  const body = {
    job_id: job.id,
    bucket,
    timeout_seconds: job.timeoutSeconds ?? (job.route === "ingest" ? 1200 : 300),
  };
  if (env.DRY_RUN === "1") {
    logLine({
      cron,
      repo: job.repo,
      job: job.id,
      route: job.route,
      bucket: bucket ?? null,
      github_status: null,
      dry_run: true,
    });
    return { ok: true, status: 0, dry_run: true };
  }
  const token = env.RUNNER_AUTH_TOKEN;
  if (!token) {
    throw new Error("RUNNER_AUTH_TOKEN is required");
  }
  if (!env.TWELVEX_RUNNER) {
    throw new Error("TWELVEX_RUNNER service binding is required");
  }
  const res = await env.TWELVEX_RUNNER.fetch(
    new Request(`${TWELVEX_ORIGIN}/run/${job.route}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }),
  );
  const text = await res.text().catch(() => "");
  let parsed: TwelveXAccept = {};
  try {
    parsed = JSON.parse(text) as TwelveXAccept;
  } catch {
    parsed = {};
  }
  logLine({
    cron,
    repo: job.repo,
    job: job.id,
    route: job.route,
    github_status: null,
    runner_status: res.status,
    exit_code: typeof parsed.exit_code === "number" ? parsed.exit_code : null,
    duration_ms: typeof parsed.duration_ms === "number" ? parsed.duration_ms : null,
    alert: typeof parsed.alert === "string" ? parsed.alert : null,
    dry_run: false,
  });
  if (res.status !== 200 || typeof parsed.exit_code !== "number") {
    throw new Error(`twelvex-runner dispatch failed for ${job.id}: HTTP ${res.status}`);
  }
  const quietAuth = job.route === "ingest" && parsed.exit_code === 2;
  if (parsed.exit_code !== 0 && !quietAuth) {
    throw new Error(`twelvex-runner ${job.id} exit ${parsed.exit_code}`);
  }
  return { ok: true, status: res.status, dry_run: false };
}
