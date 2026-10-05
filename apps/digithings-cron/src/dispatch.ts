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
 * Stable prefix on the undeclared-input refusal so POST /kick can answer a
 * legible 400 undeclared_workflow_input instead of the bare 500 that an
 * unrecognised GitHub 422 used to become. Keep in sync with the throw in
 * dispatchGithub and with the prefix check in POST /kick.
 */
export const UNDECLARED_INPUT = "undeclared_workflow_input";

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

/**
 * The input keys a GitHub 422 blames for an undeclared key, [] when the
 * refusal is recognised but spells the keys in a shape we do not parse, or
 * null when the body is some other 422 entirely (so the caller leaves it on
 * the existing paths).
 *
 * GitHub has shipped two spellings and both carry the same marker:
 *   Unexpected inputs provided to workflow: ["dates"]
 *   Unexpected inputs provided to workflow: workflow_dispatch: unexpected key(s) 'dates', relative to 'a'
 * Naming the keys is a nicety, not the gate. The marker alone already turns
 * the 500 into a 400, so a future spelling degrades to a message without the
 * key list instead of back to an opaque 500.
 */
function undeclaredInputKeys(body: string): string[] | null {
  if (!body.toLowerCase().includes("unexpected inputs provided")) return null;

  // Scan string VALUES rather than the raw text. GitHub puts the refusal in a
  // `message` field, but that field is neither guaranteed nor top-level, and
  // on a JSON body whose object keys happen to precede the message a raw scan
  // would read a field name as the offending input name.
  for (const candidate of messageCandidates(body)) {
    if (!candidate.toLowerCase().includes("unexpected inputs provided")) continue;
    const keys = keysFromMessage(candidate);
    if (keys.length > 0) return keys;
  }

  return [];
}

/** Every string in a JSON body, or `[body]` when it is not JSON. */
function messageCandidates(body: string): string[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return [body];
  }
  const strings: string[] = [];
  const collect = (node: unknown): void => {
    if (typeof node === "string") strings.push(node);
    else if (Array.isArray(node)) node.forEach(collect);
    else if (node !== null && typeof node === "object") {
      for (const value of Object.values(node)) collect(value);
    }
  };
  collect(parsed);
  return strings;
}

function keysFromMessage(message: string): string[] {
  // Quotes and backslashes terminate a token, because an undecoded body can
  // still carry JSON escaping here. This is a tokeniser, not a whitelist of
  // GitHub's input-name charset, so it does not reject a key it should not.
  const quoted = (s: string): string[] =>
    [...s.matchAll(/["']([^"'\\]+)["']/g)].map((m) => m[1]);

  for (const bracketed of message.matchAll(/\[[^\]]*\]/g)) {
    const keys = quoted(bracketed[0]);
    if (keys.length > 0) return keys;
  }

  const relative = message.match(/unexpected key\(s\)\s+(.*?)(?:,?\s+relative to\b|$)/is);
  if (relative) {
    const keys = quoted(relative[1]);
    if (keys.length > 0) return keys;
  }

  return [];
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
  // What this dispatch targets, in the words the refusal messages use. Only
  // the workflow_dispatch branch sends inputs, so a 422 blaming an input key
  // can only come from there, but both branches set this so the label can
  // never name the wrong target.
  let target: string;

  if (job.kind === "workflow_dispatch" || job.kind === "container" || job.kind === "probe") {
    if (!job.workflow || !job.ref) {
      throw new Error(`job ${job.id}: workflow_dispatch requires workflow and ref`);
    }
    url = workflowDispatchUrl(job.repo, job.workflow);
    target = `${job.workflow} on ref ${job.ref}`;
    // Per-request args are merged over the row's static inputs, not substituted
    // for them: a kick that passes only `dates` must still carry the row's
    // `backfill_snapshots`. Keys the job never declared still reach the
    // workflow, so callers own key correctness (GitHub answers 422 otherwise).
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
    body = { ref: job.ref, inputs };
  } else {
    if (!job.event_type) {
      throw new Error(`job ${job.id}: repository_dispatch requires event_type`);
    }
    url = repositoryDispatchUrl(job.repo);
    body = { event_type: job.event_type, client_payload: {} };
    target = `repository_dispatch ${job.event_type} on ${job.repo}`;
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

    // A 422 blaming an undeclared input key is the operator naming a key the
    // workflow does not declare, not a transient fault. Retrying it would
    // repeat the same refusal, so it fails closed on the first attempt like
    // the guard above. The message is the whole point: index.ts hands it to
    // the operator as the /kick 400 detail, verbatim.
    //
    // Placed FIRST, above the benign-422 and rate-limit checks, because the
    // marker is the one thing the operator can act on. GitHub does not send
    // these together, so the order is a deliberate tie-break rather than a
    // claim about GitHub: if a body ever carried both an undeclared key and
    // "already running", the bad key must still be reported, or the row
    // returns ok forever and the operator never learns the key is wrong.
    const undeclared = undeclaredInputKeys(text);
    if (undeclared !== null) {
      const named = undeclared.length > 0 ? `: ${undeclared.join(", ")}` : "";
      logLine({
        cron,
        repo: job.repo,
        job: job.id,
        github_status: status,
        dry_run: false,
        note: "undeclared_workflow_input",
        undeclared_keys: undeclared,
        error: text.slice(0, 500),
      });
      throw new Error(
        `${UNDECLARED_INPUT}: job ${job.id}: ${target} does not declare the ` +
          `input key(s)${named}. GitHub refused the dispatch, so no run started.`,
      );
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
