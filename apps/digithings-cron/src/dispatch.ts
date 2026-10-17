/**
 * Dispatch helpers for digithings-cron.
 * workflow_dispatch / repository_dispatch stay on GitHub.
 * kind "container" POSTs the private digiquant-runner over the RUNNER binding
 * unless the job id is listed in GITHUB_OVERRIDE_JOBS (default empty).
 * kind "probe" fetches public URLs inside this Worker. It does not call
 * RUNNER or api.github.com unless that same override list names the job id.
 * kind "watch" (DIG-3065) READS digiquant-runner over the RUNNER binding and
 * raises on GitHub when a run is open past its deadline. It never POSTs to
 * /v1/jobs, so it has nothing to start, re-kick or re-run.
 */
import type { Env } from "./env";
import { houseRunDeadlineSeconds, type Job } from "./jobs";
import { checkHouseRuns, WATCH_TARGET, type HouseRunCheckResult } from "./house-run-watch";
import { probeUrls, runProbe } from "./probe";
import { dispatchTwelvex } from "./twelvex-dispatch";
import { runTwelvexWatch, sessionCatchupDue, type WatchOutcome } from "./twelvex-watch";

const GH_API = "https://api.github.com";
const GH_API_VERSION = "2022-11-28";
const MAX_ATTEMPTS = 3;
const RUNNER_URL = "https://digiquant-runner/v1/jobs";

export type DispatchResult = {
  ok: boolean;
  status: number;
  dry_run: boolean;
  /** Present only on a container accept. Omitted on the GitHub path. */
  run_id?: string;
  /** accepted | already_running | duplicate | skipped. Omitted on the GitHub path. */
  container_status?: string;
  /** Set only on the watch path (DIG-3065). Absent everywhere else. */
  watch?: HouseRunCheckResult;
  /** Set only on the twelvex-watch path. */
  twelvex?: WatchOutcome;
  /** Set when a gate skipped a workflow_dispatch. */
  gated?: string;
};

export function workflowDispatchUrl(repo: string, workflow: string): string {
  return `${GH_API}/repos/${repo}/actions/workflows/${workflow}/dispatches`;
}

export function repositoryDispatchUrl(repo: string): string {
  return `${GH_API}/repos/${repo}/dispatches`;
}

/**
 * The 422 bodies that mean "GitHub declined, but nothing is wrong" — a run for
 * this ref is already in flight. Deliberately narrow: it is matched against a
 * live response body, so a wider net would quietly reclassify a real refusal as
 * a benign one and report a dispatch that never started as a success.
 *
 * A workflow disabled with `disabled_manually` is a 422 too, but its body is
 * `Cannot trigger a 'workflow_dispatch' on a disabled workflow`, which matches
 * none of these substrings. That is intended, not an oversight: such a dispatch
 * is a failure (502 on POST /backfill) whose claim is released, so the date stays
 * dispatchable. Widening this list to cover it needs the same evidence as any
 * other change to a live-body heuristic — see DIG-1227.
 */
function isBenign422(body: string): boolean {
  const lower = body.toLowerCase();
  return (
    lower.includes("already queued") ||
    lower.includes("already running") ||
    lower.includes("workflow is already running")
  );
}

function isRateLimited(status: number, body: string): boolean {
  const lower = body.toLowerCase();
  return (
    status === 429 ||
    ((status === 403 || status === 422) &&
      (lower.includes("rate limit") || lower.includes("secondary rate limit")))
  );
}

/** Error prefix for a 422 that refuses a workflow input GitHub cannot see. */
export const UNDECLARED_INPUT = "undeclared_workflow_input";

/** Lower-cased fragment of GitHub's message for that 422. */
const UNDECLARED_INPUT_MARKER = "unexpected inputs provided";

/**
 * Strings inside a GitHub error body that may carry the message.
 * Only top-level string values are collected, never object field names: a
 * field name is GitHub's own schema key, not a workflow input. A body that is
 * not JSON is used as-is.
 */
function messageCandidates(body: string): string[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return [body];
  }
  if (typeof parsed === "string") return [parsed];
  if (parsed === null || typeof parsed !== "object") return [body];
  const strings = Object.values(parsed as Record<string, unknown>).filter(
    (value): value is string => typeof value === "string",
  );
  return strings.length > 0 ? strings : [body];
}

/** Quoted tokens inside the first [...] group, as in ["bucket"]. */
function bracketedKeys(message: string): string[] {
  const group = /\[[^\]]*\]/.exec(message);
  if (!group) return [];
  return Array.from(group[0].matchAll(/["']([^"'\\]+)["']/g), (match) => match[1]);
}

/** `unexpected key(s) bucket, bucket2 relative to the expected inputs`. */
function trailingKeys(message: string): string[] {
  const match = /unexpected key\(s\)\s+(.+?)(?:,?\s+relative to\b|$)/is.exec(message);
  if (!match) return [];
  return match[1]
    .split(",")
    .map((key) => key.trim().replace(/^["']|["']$/g, ""))
    .filter((key) => key.length > 0);
}

function keysFromMessage(message: string): string[] {
  const bracketed = bracketedKeys(message);
  return bracketed.length > 0 ? bracketed : trailingKeys(message);
}

/**
 * Input keys GitHub refused, or null when this body is not that refusal and
 * the caller must leave every other 422 alone. [] means recognised but nothing
 * parseable, so the caller can still refuse loudly without naming a key it
 * never actually read.
 */
function undeclaredInputKeys(body: string): string[] | null {
  if (!body.toLowerCase().includes(UNDECLARED_INPUT_MARKER)) return null;
  for (const message of messageCandidates(body)) {
    const keys = keysFromMessage(message);
    if (keys.length > 0) return keys;
  }
  return [];
}

function retryDelayMs(response: Response, attempt: number): number {
  const retryAfter = response.headers.get("Retry-After");
  if (retryAfter === null) return attempt * 1_000;
  const seconds = Number(retryAfter);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.min(seconds * 1_000, 30_000);
  return attempt * 1_000;
}

function logLine(fields: Record<string, unknown>): void {
  console.log(JSON.stringify(fields));
}

/** Comma-separated job ids. Empty (the default) never calls api.github.com. */
export function githubOverrideIds(env: Env): string[] {
  return (env.GITHUB_OVERRIDE_JOBS ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

function usesGithub(job: Job, env: Env): boolean {
  // "watch" belongs on this arm (DIG-3065). Without it a watch row would fall
  // through to `return true` and be dispatched to GitHub as a workflow — the
  // exact failure the arm exists to prevent, since a watch job's whole contract
  // is that it never starts anything.
  if (
    job.kind === "container" ||
    job.kind === "probe" ||
    job.kind === "watch" ||
    job.kind === "twelvex-watch" ||
    job.kind === "twelvex"
  ) {
    return githubOverrideIds(env).includes(job.id);
  }
  return true;
}

type ContainerAccept = {
  ok?: boolean;
  run_id?: string;
  status?: string;
};

function isContainerSuccess(
  status: number,
  body: ContainerAccept,
): body is {
  ok: true;
  run_id: string;
  status: "accepted" | "already_running" | "duplicate" | "skipped";
} {
  return (
    status === 202 &&
    body.ok === true &&
    typeof body.run_id === "string" &&
    (body.status === "accepted" ||
      body.status === "already_running" ||
      body.status === "duplicate" ||
      body.status === "skipped")
  );
}

async function dispatchContainer(
  env: Env,
  job: Job,
  cron: string,
  scheduledTime: number,
  args: Record<string, string>,
): Promise<DispatchResult> {
  if (!job.command || !job.concurrency || job.timeoutSeconds === undefined) {
    throw new Error(`job ${job.id}: container requires command, concurrency, and timeoutSeconds`);
  }
  const body = {
    job_id: job.id,
    command: job.command,
    args,
    concurrency: job.concurrency,
    timeout_seconds: job.timeoutSeconds,
    code_ref: "main" as const,
    cron,
    scheduled_time: scheduledTime,
    idempotency_key: `${job.id}:${scheduledTime}`,
  };
  if (env.DRY_RUN === "1") {
    logLine({
      cron,
      repo: job.repo,
      job: job.id,
      command: job.command,
      github_status: null,
      dry_run: true,
      body,
    });
    return { ok: true, status: 0, dry_run: true };
  }
  const token = env.RUNNER_AUTH_TOKEN;
  if (!token) {
    throw new Error("RUNNER_AUTH_TOKEN is required");
  }
  if (!env.RUNNER) {
    throw new Error("RUNNER service binding is required");
  }
  const res = await env.RUNNER.fetch(RUNNER_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const text = await res.text().catch(() => "");
  let parsed: ContainerAccept = {};
  try {
    parsed = JSON.parse(text) as ContainerAccept;
  } catch {
    parsed = {};
  }
  if (isContainerSuccess(res.status, parsed)) {
    logLine({
      cron,
      repo: job.repo,
      job: job.id,
      command: job.command,
      github_status: null,
      runner_status: res.status,
      container_status: parsed.status,
      run_id: parsed.run_id,
      dry_run: false,
    });
    return {
      ok: true,
      status: res.status,
      dry_run: false,
      run_id: parsed.run_id,
      container_status: parsed.status,
    };
  }
  logLine({
    cron,
    repo: job.repo,
    job: job.id,
    github_status: null,
    runner_status: res.status,
    dry_run: false,
    error: text.slice(0, 500),
  });
  throw new Error(`digiquant-runner dispatch failed for ${job.id}: HTTP ${res.status}`);
}

async function dispatchProbe(env: Env, job: Job, cron: string): Promise<DispatchResult> {
  if (job.probe !== "site" && job.probe !== "stack") {
    throw new Error(`job ${job.id}: probe requires probe "site" or "stack"`);
  }
  const urls = probeUrls(job.probe);
  if (env.DRY_RUN === "1") {
    logLine({
      cron,
      repo: job.repo,
      job: job.id,
      probe: job.probe,
      github_status: null,
      dry_run: true,
      urls,
    });
    return { ok: true, status: 0, dry_run: true };
  }
  await runProbe(job.probe, fetch, new Date());
  logLine({
    cron,
    repo: job.repo,
    job: job.id,
    probe: job.probe,
    github_status: null,
    dry_run: false,
    urls,
  });
  return { ok: true, status: 200, dry_run: false };
}

/**
 * Watch job (DIG-3065). Reads digiquant-runner over the RUNNER binding and
 * raises one GitHub issue per run the runner still holds open past its deadline.
 *
 * Three deliberate properties:
 *  - Read-only. Nothing here POSTs to /v1/jobs. The only writes are the label
 *    and the issue, both on GitHub.
 *  - Fail quiet. An unreadable health or run response is reported as unreadable
 *    and never raised, so a transport fault cannot manufacture an alarm.
 *  - No deadline of its own. It is read from the house-run job row, so the 14400
 *    has one home. A missing row means no evaluation, not a guessed deadline.
 */
async function dispatchWatch(
  env: Env,
  job: Job,
  cron: string,
  scheduledTime: number,
): Promise<DispatchResult> {
  if (job.watch !== WATCH_TARGET) {
    throw new Error(`job ${job.id}: watch requires watch "${WATCH_TARGET}"`);
  }
  const timeoutSeconds = houseRunDeadlineSeconds();
  if (timeoutSeconds === undefined) {
    console.error(
      JSON.stringify({ cron, repo: job.repo, job: job.id, error: "house_run_row_missing" }),
    );
    return { ok: false, status: 0, dry_run: false };
  }
  if (env.DRY_RUN === "1") {
    logLine({
      cron,
      repo: job.repo,
      job: job.id,
      watch: job.watch,
      dry_run: true,
    });
    return { ok: true, status: 0, dry_run: true };
  }
  if (!env.RUNNER) {
    throw new Error(`job ${job.id}: the RUNNER binding is required for watch jobs`);
  }

  const nowMs = scheduledTime > 0 ? scheduledTime : Date.now();
  const watch = await checkHouseRuns({
    fetchRunner: (input, init) => env.RUNNER!.fetch(input, init as RequestInit),
    fetchGithub: (input, init) => fetch(input, init),
    runnerToken: env.RUNNER_AUTH_TOKEN,
    githubToken: env.GH_DISPATCH_TOKEN,
    timeoutSeconds,
    nowMs,
  });
  logLine({
    cron,
    repo: job.repo,
    job: job.id,
    watch: job.watch,
    dry_run: false,
    open: watch.open,
    lost: watch.lost.length,
    unreadable: watch.unreadable.length,
    raised: watch.raised.filter((entry) => entry.raised).length,
  });
  // ok mirrors whether the check completed, not whether it found something. A
  // tick that reads the runner cleanly and finds one lost run is a healthy tick
  // that reported; callers must read watch.lost for the finding.
  return { ok: watch.ok, status: watch.ok ? 200 : 0, dry_run: false, watch };
}

/**
 * Dispatch one job.
 * Container jobs POST digiquant-runner. Accepted, already-running, duplicate, and
 * skipped 202 responses are successful. Probe jobs fetch public URLs in this
 * Worker. DRY_RUN=1 logs and does not call. A job id in GITHUB_OVERRIDE_JOBS
 * uses workflow_dispatch and logs github_override.
 * opts.args reaches every dispatch path: on a GitHub row it overrides the
 * row's static inputs per key, on a container row it is sent as args.
 */
export async function dispatch(
  env: Env,
  job: Job,
  cron: string,
  scheduledTime = 0,
  opts: { args?: Record<string, string>; force?: boolean } = {},
): Promise<DispatchResult> {
  if (usesGithub(job, env)) {
    if (job.gate === "twelvex-session-due" && !opts.force && env.DRY_RUN !== "1") {
      const verdict = await sessionCatchupDue(
        (input, init) => fetch(input, init),
        env.GH_DISPATCH_TOKEN,
        scheduledTime > 0 ? scheduledTime : Date.now(),
      );
      logLine({ cron, repo: job.repo, job: job.id, gate: job.gate, due: verdict.due, reason: verdict.reason });
      if (!verdict.due) {
        return { ok: true, status: 0, dry_run: false, gated: verdict.reason };
      }
    }
    if (
      job.kind === "container" ||
      job.kind === "probe" ||
      job.kind === "watch" ||
      job.kind === "twelvex-watch" ||
      job.kind === "twelvex"
    ) {
      console.error(
        JSON.stringify({
          cron,
          repo: job.repo,
          job: job.id,
          github_override: true,
          error: "github_override",
        }),
      );
    }
    return dispatchGithub(env, job, cron, opts.args ?? {});
  }
  if (job.kind === "probe") {
    return dispatchProbe(env, job, cron);
  }
  if (job.kind === "watch") {
    return dispatchWatch(env, job, cron, scheduledTime);
  }
  if (job.kind === "twelvex") {
    return dispatchTwelvex(env, job, cron);
  }
  if (job.kind === "twelvex-watch") {
    if (!job.twelvexWatch) throw new Error(`job ${job.id}: twelvex-watch requires twelvexWatch`);
    if (env.DRY_RUN === "1") {
      logLine({ cron, repo: job.repo, job: job.id, twelvex_watch: job.twelvexWatch, dry_run: true });
      return { ok: true, status: 0, dry_run: true };
    }
    const out = await runTwelvexWatch(
      job.twelvexWatch,
      (input, init) => fetch(input, init),
      env.GH_DISPATCH_TOKEN,
      scheduledTime > 0 ? scheduledTime : Date.now(),
    );
    logLine({ cron, repo: job.repo, job: job.id, twelvex_watch: job.twelvexWatch, ...out });
    return { ok: out.ok, status: out.ok ? 200 : 0, dry_run: false, twelvex: out };
  }
  return dispatchContainer(env, job, cron, scheduledTime, opts.args ?? {});
}

/** Identifies one GitHub call in log lines and error messages. */
type DispatchContext = {
  cron: string;
  repo: string;
  job: string;
};

/**
 * POST one GitHub dispatch, with the shared retry / benign-422 / rate-limit
 * handling. Every api.github.com write in this Worker goes through here, so the
 * manual-kick surface and the cron surface cannot drift on error handling.
 */
async function postGithub(
  env: Env,
  url: string,
  body: Record<string, unknown>,
  at: DispatchContext,
  target: string,
): Promise<DispatchResult> {
  const token = env.GH_DISPATCH_TOKEN;
  if (!token) {
    throw new Error("GH_DISPATCH_TOKEN is required when DRY_RUN is not 1");
  }

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": GH_API_VERSION,
        "Content-Type": "application/json",
        "User-Agent": "digithings-cron",
      },
      body: JSON.stringify(body),
    });
    const status = res.status;
    const text = await res.text().catch(() => "");

    if (status === 204 || status === 200) {
      logLine({
        cron: at.cron,
        repo: at.repo,
        job: at.job,
        github_status: status,
        dry_run: false,
        attempt,
      });
      return { ok: true, status, dry_run: false };
    }

    // Ahead of the benign and rate-limit checks on purpose. An undeclared input is
    // a deterministic refusal: it is not benign and retrying cannot change it.
    const undeclared = undeclaredInputKeys(text);
    if (undeclared !== null) {
      const named = undeclared.length > 0 ? `: ${undeclared.join(", ")}` : "";
      logLine({
        cron: at.cron,
        repo: at.repo,
        job: at.job,
        github_status: status,
        dry_run: false,
        note: UNDECLARED_INPUT,
        undeclared_keys: undeclared,
        error: text.slice(0, 500),
      });
      throw new Error(
        `${UNDECLARED_INPUT}: job ${at.job}: ${target} does not declare the input key(s)${named}. GitHub refused the dispatch, so no run started.`,
      );
    }

    if (status === 422 && isBenign422(text)) {
      logLine({
        cron: at.cron,
        repo: at.repo,
        job: at.job,
        github_status: status,
        dry_run: false,
        note: "benign_422",
      });
      return { ok: true, status, dry_run: false };
    }

    if (isRateLimited(status, text) && attempt < MAX_ATTEMPTS) {
      const delayMs = retryDelayMs(res, attempt);
      logLine({
        cron: at.cron,
        repo: at.repo,
        job: at.job,
        github_status: status,
        dry_run: false,
        retry_attempt: attempt + 1,
        delay_ms: delayMs,
      });
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      continue;
    }

    logLine({
      cron: at.cron,
      repo: at.repo,
      job: at.job,
      github_status: status,
      dry_run: false,
      error: text.slice(0, 500),
    });
    throw new Error(`GitHub dispatch failed for ${at.job}: HTTP ${status}`);
  }
  throw new Error(`GitHub dispatch failed for ${at.job}: retries exhausted`);
}

export type WorkflowDispatchTarget = {
  /** Cron label for the log line; the manual surface has no cron of its own. */
  cron: string;
  /** Job-shaped identifier used in log lines and error messages. */
  label: string;
  repo: string;
  workflow: string;
  ref: string;
  inputs?: Record<string, unknown>;
};

/**
 * workflow_dispatch for a caller that is not a JOBS row — today that is only
 * POST /backfill. Same POST, same retries, same benign-422 handling as the cron
 * surface; it simply has no row behind it and therefore no clock.
 */
export async function dispatchWorkflow(
  env: Env,
  target: WorkflowDispatchTarget,
): Promise<DispatchResult> {
  const url = workflowDispatchUrl(target.repo, target.workflow);
  const body: Record<string, unknown> = { ref: target.ref, inputs: target.inputs ?? {} };
  const at: DispatchContext = { cron: target.cron, repo: target.repo, job: target.label };

  if (env.DRY_RUN === "1") {
    logLine({
      cron: at.cron,
      repo: at.repo,
      job: at.job,
      github_status: null,
      dry_run: true,
      url,
      body,
    });
    return { ok: true, status: 0, dry_run: true };
  }

  return postGithub(env, url, body, at, `${target.workflow} on ref ${target.ref}`);
}

async function dispatchGithub(
  env: Env,
  job: Job,
  cron: string,
  args: Record<string, string> = {},
): Promise<DispatchResult> {
  // A /kick arg is what the caller asked for right now, so it wins over the
  // row's static value. Keys the caller did not mention keep the row's value,
  // so a partial override cannot silently blank the rest of the inputs.
  const inputs: Record<string, string> = { ...(job.inputs ?? {}), ...args };
  if (job.kind !== "repository_dispatch") {
    if (!job.workflow || !job.ref) {
      throw new Error(`job ${job.id}: workflow_dispatch requires workflow and ref`);
    }
    return dispatchWorkflow(env, {
      cron,
      label: job.id,
      repo: job.repo,
      workflow: job.workflow,
      ref: job.ref,
      inputs,
    });
  }

  if (!job.event_type) {
    throw new Error(`job ${job.id}: repository_dispatch requires event_type`);
  }
  const url = repositoryDispatchUrl(job.repo);
  const body: Record<string, unknown> = { event_type: job.event_type, client_payload: inputs };

  if (env.DRY_RUN === "1") {
    logLine({
      cron,
      repo: job.repo,
      job: job.id,
      github_status: null,
      dry_run: true,
      url,
      body,
    });
    return { ok: true, status: 0, dry_run: true };
  }

  return postGithub(
    env,
    url,
    body,
    { cron, repo: job.repo, job: job.id },
    `repository_dispatch ${job.event_type} on ${job.repo}`,
  );
}
