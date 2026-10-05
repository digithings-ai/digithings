/**
 * Dispatch helpers for digithings-cron.
 * workflow_dispatch / repository_dispatch stay on GitHub.
 * kind "container" POSTs the private digiquant-runner over the RUNNER binding
 * unless the job id is listed in GITHUB_OVERRIDE_JOBS (default empty).
 * kind "probe" fetches public URLs inside this Worker. It does not call
 * RUNNER or api.github.com unless that same override list names the job id.
 */
import type { Env } from "./env";
import type { Job } from "./jobs";
import { probeUrls, runProbe } from "./probe";

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
};

/**
 * Stable prefix on the guard refusal so POST /kick can answer a legible
 * 400 missing_required_arg instead of a bare 500. Keep in sync with the throw
 * in dispatchGithub.
 */
export const MISSING_REQUIRED_ARG = "missing_required_arg";

/**
 * Stable prefix on the per-row `/kick` arg allowlist refusal, so POST /kick
 * answers a legible 400 kick_arg_not_allowed instead of a bare 500. Keep in
 * sync with the throw in dispatchGithub.
 */
export const KICK_ARG_NOT_ALLOWED = "kick_arg_not_allowed";

export function workflowDispatchUrl(repo: string, workflow: string): string {
  return `${GH_API}/repos/${repo}/actions/workflows/${workflow}/dispatches`;
}

export function repositoryDispatchUrl(repo: string): string {
  return `${GH_API}/repos/${repo}/dispatches`;
}

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
  if (job.kind === "container" || job.kind === "probe") {
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
 * Dispatch one job.
 * Container jobs POST digiquant-runner. Accepted, already-running, duplicate, and
 * skipped 202 responses are successful. Probe jobs fetch public URLs in this
 * Worker. DRY_RUN=1 logs and does not call. A job id in GITHUB_OVERRIDE_JOBS
 * uses workflow_dispatch and logs github_override.
 */
export async function dispatch(
  env: Env,
  job: Job,
  cron: string,
  scheduledTime = 0,
  opts: { args?: Record<string, string> } = {},
): Promise<DispatchResult> {
  if (usesGithub(job, env)) {
    if (job.kind === "container" || job.kind === "probe") {
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
    return dispatchGithub(env, job, cron, opts.args);
  }
  if (job.kind === "probe") {
    return dispatchProbe(env, job, cron);
  }
  return dispatchContainer(env, job, cron, scheduledTime, opts.args ?? {});
}

async function dispatchGithub(
  env: Env,
  job: Job,
  cron: string,
  args: Record<string, string> = {},
): Promise<DispatchResult> {
  const dryRun = env.DRY_RUN === "1";
  let url: string;
  let body: Record<string, unknown>;

  if (job.kind === "workflow_dispatch" || job.kind === "container" || job.kind === "probe") {
    if (!job.workflow || !job.ref) {
      throw new Error(`job ${job.id}: workflow_dispatch requires workflow and ref`);
    }
    url = workflowDispatchUrl(job.repo, job.workflow);
    // Per-request args are merged over the row's static inputs, not substituted
    // for them: a kick that passes only `dates` must still carry the row's
    // `backfill_snapshots`. Precedence stays args-win because that is the
    // contract DIG-69/DIG-73 recorded — `start_key` must be able to ADD a key
    // the row does not declare statically. What a caller may change is bounded
    // separately, by `kickArgs` below; the merge itself is unchanged.
    const inputs = { ...(job.inputs ?? {}), ...args };
    // A row may demand a date bound (or any other key) per request. Checked on
    // the MERGED inputs, so a bound in the row's static config also satisfies
    // it, and BEFORE the dry-run branch so DRY_RUN=1 previews the refusal
    // faithfully. Presence only, deliberately: a value that is present but
    // malformed (an unpadded `2026-6-2`, a padded one) still sorts wrong
    // against run_date and over-sweeps, but tightening that would need the input
    // shape twelve-x#237 (DIG-52) settles, which is not merged yet. The
    // zero-padded-ISO requirement is documented on the row instead.
    const required = job.requiredKickArgs ?? [];
    if (required.length > 0 && !required.some((key) => (inputs[key] ?? "").trim() !== "")) {
      throw new Error(
        `${MISSING_REQUIRED_ARG}: job ${job.id}: /kick requires at least one of ` +
          `${required.join(", ")} to carry a non-empty value. With none, the ` +
          `workflow receives no date bound and re-projects every stored run_date.`,
      );
    }
    // Per-row allowlist (DIG-469). Args-win above means a caller with
    // CRON_KICK_SECRET could otherwise rewrite ANY of this row's static
    // inputs — flip `dry_run` on agent-pr-finalizer, repoint `bucket` on a
    // market-context row, turn `dump_before_prune` off. `kickArgs` is the
    // row's own statement of which keys a caller may supply; `undefined`
    // means unbounded (today's behaviour, kept so a row that has no opinion
    // is not broken by this control). The row's OWN static inputs are never
    // listed there: the row decides those, not the caller. An empty list
    // accepts no per-request arg at all.
    //
    // Reads `args`, not the merged `inputs`, so it polices only what the
    // request supplied and can never refuse a row's own configuration. Order
    // matters: `requiredKickArgs` runs first so its more specific refusal —
    // "this kick is unbounded and would sweep every run_date" — stays
    // authoritative for the DIG-55 row (DIG-369 pins that response), and the
    // allowlist answers second. Both run before the dry-run branch, so
    // DRY_RUN=1 previews the refusal faithfully and nothing reaches
    // api.github.com.
    const allowed = job.kickArgs;
    if (allowed !== undefined) {
      const refused = Object.keys(args)
        .filter((key) => !allowed.includes(key))
        .sort();
      if (refused.length > 0) {
        throw new Error(
          `${KICK_ARG_NOT_ALLOWED}: job ${job.id}: /kick refused ` +
            `${refused.join(", ")}. This row accepts only ` +
            `${allowed.length > 0 ? allowed.join(", ") : "no per-request args"}` +
            `${", and the row's own static inputs are never caller-settable"}. ` +
            `Drop the arg, or add the key to the row's kickArgs in ` +
            `apps/digithings-cron/src/jobs.ts.`,
        );
      }
    }
    body = { ref: job.ref, inputs };
  } else {
    if (!job.event_type) {
      throw new Error(`job ${job.id}: repository_dispatch requires event_type`);
    }
    url = repositoryDispatchUrl(job.repo);
    body = { event_type: job.event_type, client_payload: {} };
  }

  if (dryRun) {
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
        cron,
        repo: job.repo,
        job: job.id,
        github_status: status,
        dry_run: false,
        attempt,
      });
      return { ok: true, status, dry_run: false };
    }

    if (status === 422 && isBenign422(text)) {
      logLine({
        cron,
        repo: job.repo,
        job: job.id,
        github_status: status,
        dry_run: false,
        note: "benign_422",
      });
      return { ok: true, status, dry_run: false };
    }

    if (isRateLimited(status, text) && attempt < MAX_ATTEMPTS) {
      const delayMs = retryDelayMs(res, attempt);
      logLine({
        cron,
        repo: job.repo,
        job: job.id,
        github_status: status,
        dry_run: false,
        retry_attempt: attempt + 1,
        delay_ms: delayMs,
      });
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      continue;
    }

    logLine({
      cron,
      repo: job.repo,
      job: job.id,
      github_status: status,
      dry_run: false,
      error: text.slice(0, 500),
    });
    throw new Error(`GitHub dispatch failed for ${job.id}: HTTP ${status}`);
  }
  throw new Error(`GitHub dispatch failed for ${job.id}: retries exhausted`);
}
