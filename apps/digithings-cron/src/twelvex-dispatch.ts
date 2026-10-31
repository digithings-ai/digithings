/**
 * Dispatch twelve-x ingest and heartbeat to the twelvex-runner Worker.
 * GITHUB_OVERRIDE_JOBS still sends the same job id to workflow_dispatch.
 * DRY_RUN=1 logs the route and does not call. The log line carries the one
 * line reason of a failed run and no secret. It carries no log tail.
 */
import type { Env } from "./env";
import type { Job } from "./jobs";
import type { DispatchResult } from "./dispatch";

const TWELVEX_ORIGIN = "https://twelvex-runner";
/** The reason the runner reports is one line; the error column is one line. */
const REASON_LIMIT = 400;

type TwelveXAccept = {
  ok?: boolean;
  exit_code?: number;
  duration_ms?: number;
  alert?: string;
  reason?: string | null;
};

function logLine(fields: Record<string, unknown>): void {
  console.log(JSON.stringify(fields));
}

/**
 * The reason a run failed, on one line. The runner already redacted the
 * container log tail before it left the image, so this is a cause, never a
 * secret. A blank reason is no reason.
 */
export function reasonFrom(parsed: TwelveXAccept): string | null {
  if (typeof parsed.reason === "string") {
    const one = parsed.reason.replace(/\s+/g, " ").trim();
    if (one) return one.slice(0, REASON_LIMIT);
  }
  if (typeof parsed.log_tail !== "string") return null;
  const tail = parsed.log_tail;
  const token = "MARKET_CONTEXT_VERDICT=";
  const at = tail.lastIndexOf(token);
  if (at !== -1) {
    const line = tail.slice(at + token.length).split("\n")[0].replace(/\s+/g, " ").trim();
    if (line) return line.slice(0, REASON_LIMIT);
  }
  const rows = tail.split("\n");
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const marker = "market_context:";
    const pos = rows[index].lastIndexOf(marker);
    if (pos === -1) continue;
    const rest = rows[index].slice(pos + marker.length).replace(/\s+/g, " ").trim();
    if (rest) return rest.slice(0, REASON_LIMIT);
  }
  return null;
}

export async function dispatchTwelvex(
  env: Env,
  job: Job,
  cron: string,
): Promise<DispatchResult> {
  if (job.route !== "ingest" && job.route !== "heartbeat" && job.route !== "session") {
    throw new Error(`job ${job.id}: twelvex requires route ingest, heartbeat or session`);
  }
  const bucket = job.inputs?.bucket;
  const session = job.inputs?.session;
  // The workflow's optional backfill date. Only the session route takes it,
  // and the daily crons carry none, so the key is left out of the body
  // entirely and the graph takes its forward path. A malformed date in a job
  // row fails the job here, before the runner is called.
  // The runner trims and reads an empty date as no date, so the dispatcher
  // does the same: a padded value is forwarded clean, and an empty one is
  // left out of the body instead of failing the job.
  const rawRunDate = job.route === "session" ? job.inputs?.run_date : undefined;
  const trimmedRunDate = rawRunDate?.trim();
  const runDate = trimmedRunDate ? trimmedRunDate : undefined;
  if (runDate !== undefined && !/^\d{4}-\d{2}-\d{2}$/.test(runDate)) {
    // The shape only. The runner is the authority on the date itself and
    // answers 400 invalid_run_date for a day that does not exist.
    throw new Error(`job ${job.id}: run_date must look like a calendar date (YYYY-MM-DD)`);
  }
  const body = {
    job_id: job.id,
    bucket,
    session,
    run_date: runDate,
    timeout_seconds:
      job.timeoutSeconds ??
      (job.route === "ingest" ? 1200 : job.route === "session" ? 7200 : 300),
  };
  if (env.DRY_RUN === "1") {
    logLine({
      cron,
      repo: job.repo,
      job: job.id,
      route: job.route,
      bucket: bucket ?? null,
      session: session ?? null,
      github_status: null,
      dry_run: true,
    });
    return { ok: true, status: 0, dry_run: true };
  }
  // Dedicated secret first: rotating the twelve-x runner token must never touch
  // the RUNNER_AUTH_TOKEN that digiquant-runner validates. The fallback keeps a
  // single-secret deployment working during the transition.
  // `||`, not `??`: an empty secret is not a usable token, so it falls back
  // rather than sending `Bearer ` to the runner.
  const token = env.TWELVEX_RUNNER_AUTH || env.RUNNER_AUTH_TOKEN;
  if (!token) {
    throw new Error("TWELVEX_RUNNER_AUTH or RUNNER_AUTH_TOKEN is required");
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
  const reason = reasonFrom(parsed);
  logLine({
    cron,
    repo: job.repo,
    job: job.id,
    route: job.route,
    github_status: null,
    runner_status: res.status,
    exit_code: typeof parsed.exit_code === "number" ? parsed.exit_code : null,
    duration_ms: typeof parsed.duration_ms === "number" ? parsed.duration_ms : null,
    reason,
    alert: typeof parsed.alert === "string" ? parsed.alert : null,
    dry_run: false,
  });
  if (res.status !== 200 || typeof parsed.exit_code !== "number") {
    throw new Error(`twelvex-runner dispatch failed for ${job.id}: HTTP ${res.status}`);
  }
  const quietAuth = job.route === "ingest" && parsed.exit_code === 2;
  if (parsed.exit_code !== 0 && !quietAuth) {
    // The reason travels with the error: this message is what the run watch
    // reads from the Worker error column, and an exit code alone names no
    // cause.
    throw new Error(
      reason
        ? `twelvex-runner ${job.id} exit ${parsed.exit_code}: ${reason}`
        : `twelvex-runner ${job.id} exit ${parsed.exit_code}`,
    );
  }
  return { ok: true, status: res.status, dry_run: false };
}
