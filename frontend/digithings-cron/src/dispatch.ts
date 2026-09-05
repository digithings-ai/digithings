/**
 * GitHub Actions dispatch helpers for digithings-cron.
 */
import type { Env } from "./env";
import type { Job } from "./jobs";

const GH_API = "https://api.github.com";
const GH_API_VERSION = "2022-11-28";
const MAX_ATTEMPTS = 3;

export type DispatchResult = {
  ok: boolean;
  status: number;
  dry_run: boolean;
};

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
  const seconds = Number(response.headers.get("Retry-After"));
  if (Number.isFinite(seconds) && seconds >= 0) return Math.min(seconds * 1_000, 30_000);
  return attempt * 1_000;
}

function logLine(fields: Record<string, unknown>): void {
  console.log(JSON.stringify(fields));
}

/**
 * Dispatch one job. Treats 200/204 as success and retries rate limits.
 * A 422 that explicitly says the workflow is already queued/running is benign.
 * DRY_RUN=1 logs the intended POST without calling GitHub.
 */
export async function dispatch(env: Env, job: Job, cron: string): Promise<DispatchResult> {
  const dryRun = env.DRY_RUN === "1";
  let url: string;
  let body: Record<string, unknown>;

  if (job.kind === "workflow_dispatch") {
    if (!job.workflow || !job.ref) {
      throw new Error(`job ${job.id}: workflow_dispatch requires workflow and ref`);
    }
    url = workflowDispatchUrl(job.repo, job.workflow);
    body = { ref: job.ref, inputs: job.inputs ?? {} };
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
