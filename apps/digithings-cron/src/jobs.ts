/**
 * Typed job map for digithings-cron.
 * Each enabled job.cron must appear in wrangler.toml [triggers] crons.
 */
export type JobKind = "workflow_dispatch" | "repository_dispatch" | "container" | "probe";

export type Job = {
  id: string;
  cron: string;
  repo: "digithings-ai/digithings" | "digithings-ai/twelve-x";
  kind: JobKind;
  workflow?: string;
  inputs?: Record<string, string>;
  event_type?: string;
  ref?: "develop" | "main";
  etOpenGate?: boolean;
  enabled: boolean;
  /** Set when kind is "container". Must exist in digiquant-runner commands.json. */
  command?: string;
  /** Same-group overlap returns already_running (benign, like GHA 422). */
  concurrency?: string;
  timeoutSeconds?: number;
  /** Image pin. Phase 1 jobs use "main". */
  codeRef?: "main";
  /** Set when kind is "probe". Worker fetch; does not start the container. */
  probe?: "site" | "stack";
};

const DIGITHINGS = "digithings-ai/digithings" as const;
const TWELVE_X = "digithings-ai/twelve-x" as const;
const DEVELOP = "develop" as const;

function wd(
  id: string,
  cron: string,
  repo: Job["repo"],
  workflow: string,
  opts: {
    inputs?: Record<string, string>;
    etOpenGate?: boolean;
    enabled?: boolean;
  } = {},
): Job {
  return {
    id,
    cron,
    repo,
    kind: "workflow_dispatch",
    workflow,
    inputs: opts.inputs,
    ref: DEVELOP,
    etOpenGate: opts.etOpenGate,
    enabled: opts.enabled ?? true,
  };
}

/** Probe job. workflow + ref stay so GITHUB_OVERRIDE_JOBS can still dispatch. */
function pj(
  id: string,
  cron: string,
  workflow: string,
  probe: "site" | "stack",
  opts: { enabled?: boolean } = {},
): Job {
  return {
    id,
    cron,
    repo: DIGITHINGS,
    kind: "probe",
    workflow,
    ref: DEVELOP,
    enabled: opts.enabled ?? true,
    probe,
  };
}

/** Container job. workflow + ref stay so GITHUB_OVERRIDE_JOBS can still dispatch. */
function cj(
  id: string,
  cron: string,
  workflow: string,
  command: string,
  concurrency: string,
  timeoutSeconds: number,
  opts: {
    inputs?: Record<string, string>;
    etOpenGate?: boolean;
    enabled?: boolean;
  } = {},
): Job {
  return {
    id,
    cron,
    repo: DIGITHINGS,
    kind: "container",
    workflow,
    inputs: opts.inputs,
    ref: DEVELOP,
    etOpenGate: opts.etOpenGate,
    enabled: opts.enabled ?? true,
    command,
    concurrency,
    timeoutSeconds,
    codeRef: "main",
  };
}

/** All org production clocks. Source of truth alongside wrangler [triggers]. */
export const JOBS: readonly Job[] = [
  // Resumed 2026-10-01: DigiQuant pipeline clocks live again (Human Gate unlock
  // reversing #4917). House-run is weekly Monday morning only (cost lock).
  // --- digithings: digiquant prices + market-data (container, #4761) ---
  // inputs stay for the GITHUB_OVERRIDE_JOBS workflow_dispatch path only.
  cj(
    "prices-at-open-13",
    "40 13 * * MON-FRI",
    "pipeline-digiquant-prices.yml",
    "prices-at-open",
    "digiquant-at-open",
    900,
    { inputs: { mode: "at-open" }, etOpenGate: true },
  ),
  cj(
    "prices-at-open-14",
    "40 14 * * MON-FRI",
    "pipeline-digiquant-prices.yml",
    "prices-at-open",
    "digiquant-at-open",
    900,
    { inputs: { mode: "at-open" }, etOpenGate: true },
  ),
  cj(
    "prices-fx-refresh",
    "19 */2 * * MON-FRI",
    "pipeline-digiquant-prices.yml",
    "prices-fx-candles",
    "digiquant-fx-candles",
    600,
    { inputs: { mode: "fx-refresh" } },
  ),
  cj(
    "prices-fx-refresh-sun",
    "19 22 * * SUN",
    "pipeline-digiquant-prices.yml",
    "prices-fx-candles",
    "digiquant-fx-candles",
    600,
    { inputs: { mode: "fx-refresh" } },
  ),
  cj(
    "prices-eod-macro",
    "27 21 * * MON-FRI",
    "pipeline-digiquant-prices.yml",
    "prices-eod-macro",
    "digiquant-eod-macro",
    1200,
    { inputs: { mode: "eod-macro" } },
  ),
  cj(
    "market-data-refresh-morning",
    "0 13 * * *",
    "pipeline-market-data-refresh.yml",
    "market-data-refresh",
    "market-data-refresh",
    1800,
  ),
  // --- digithings: checkpoint archive (container, #4761 Phase 4) ---
  // Clock is digithings-cron → digiquant-runner. GHA keeps workflow_dispatch only.
  cj(
    "checkpoint-archive",
    "30 13 * * *",
    "pipeline-checkpoint-archive.yml",
    "checkpoint-archive",
    "checkpoint-archive",
    3600,
  ),
  cj(
    "market-data-refresh-evening",
    "30 21 * * *",
    "pipeline-market-data-refresh.yml",
    "market-data-refresh",
    "market-data-refresh",
    1800,
  ),

  // --- digithings: house-run (container, #4761) ---
  // Live cadence: weekly Monday morning only (cost lock 2026-10-01).
  cj(
    "house-run-09",
    "17 9 * * MON",
    "pipeline-digiquant.yml",
    "house-run",
    "digiquant-pipeline",
    14400,
  ),
  // Daily 10/11/12 retries stay off (weekly Mon lock 2026-10-01).
  cj(
    "house-run-10",
    "17 10 * * *",
    "pipeline-digiquant.yml",
    "house-run",
    "digiquant-pipeline",
    14400,
    { enabled: false },
  ),
  cj(
    "house-run-11",
    "17 11 * * *",
    "pipeline-digiquant.yml",
    "house-run",
    "digiquant-pipeline",
    14400,
    { enabled: false },
  ),
  cj(
    "house-run-12",
    "17 12 * * *",
    "pipeline-digiquant.yml",
    "house-run",
    "digiquant-pipeline",
    14400,
    { enabled: false },
  ),

  // Phase 2 (#4761). Probe CLIs are on main, so this cutover stays codeRef main.
  // Do not point the container at develop.
  cj(
    "research-metrics",
    "5 22 * * *",
    "pipeline-research-metrics.yml",
    "research-metrics",
    "research-refresh-metrics",
    1200,
  ),
  cj(
    "tearsheets",
    "12 0 * * *",
    "pipeline-digiquant-tearsheets.yml",
    "tearsheets",
    "digiquant-tearsheets",
    2700,
  ),
  cj(
    "onchain",
    "40 22 * * *",
    "pipeline-digiquant-onchain.yml",
    "onchain-bitview",
    "digiquant-onchain",
    900,
  ),
  cj(
    "execution-cron-check",
    "15 12 * * *",
    "execution-cron-check.yml",
    "execution-cron-check",
    "execution-cron-check",
    600,
  ),
  wd("continuous-improvement", "8 22 * * SUN", DIGITHINGS, "pipeline-continuous-improvement.yml"),
  wd("maintenance", "8 8 * * MON", DIGITHINGS, "pipeline-maintenance.yml"),
  wd("provider-review", "9 0 * * SUN", DIGITHINGS, "pipeline-provider-review.yml"),

  // --- digithings: ops / agent / smoke (off-grid minutes) ---
  // Path A traps restored after #4967 (Approve-full). YAML is workflow_dispatch
  // only; clocks live here. dry_run must be false: workflow defaults dispatch
  // to dry_run=true and only forced live on the old GHA schedule event.
  wd("agent-pr-finalizer", "11 7 * * *", DIGITHINGS, "agent-pr-finalizer.yml", {
    inputs: { dry_run: "false" },
  }),
  wd("agent-backlog-snapshot", "13 6 * * MON", DIGITHINGS, "agent-backlog-snapshot.yml"),
  wd("ci-pr-hygiene", "21 6 * * *", DIGITHINGS, "ci-pr-hygiene.yml"),
  wd("refresh-repo-activity", "10 6 * * MON", DIGITHINGS, "refresh-repo-activity.yml"),
  wd(
    "project-enforce-assignment",
    "23 9 * * *",
    DIGITHINGS,
    "project-enforce-assignment.yml",
  ),
  pj("smoke-stack", "27 7 * * *", "smoke-stack.yml", "stack"),
  wd("security-pip-audit", "33 6 * * MON", DIGITHINGS, "security-pip-audit.yml"),
  wd("security-npm-audit", "37 6 * * MON", DIGITHINGS, "security-npm-audit.yml"),
  // Daily, not weekly: an expired credential should surface in <=24h, which is
  // the point of the canary (#3522).
  wd("token-canary", "41 6 * * *", DIGITHINGS, "token-canary.yml"),
  // Monthly names-only ageing sweep for the 90-day rotation window (#248). The
  // clock lives here and not on the workflow: develop carries no on.schedule, and
  // the workflow is workflow_dispatch only. Off :00 and off the smoke-site minute
  // so nothing lands on a shared runner's worst moment.
  wd("secret-staleness", "17 6 1 * *", DIGITHINGS, "secret-staleness-check.yml"),
  pj("smoke-site", "17 6 * * *", "smoke-site.yml", "site"),
  // Hourly answer-integrity probe against DataTap production. Clock lives here,
  // not on the workflow: develop carries no on.schedule (#DIG-306). Read-only.
  wd("datatap-answer-check", "17 * * * *", DIGITHINGS, "datatap-answer-check.yml"),

  // --- twelve-x (FX Hub) — resumed 2026-10-01 (Human Gate unlock) ---
  // digisearch_parity is not a digithings workflow (leftover sweep after #4970).
  // Add a twelve-x wd() row only with a known cron from that repo.
  wd("twelve-x-asia", "7 0 * * MON-FRI", TWELVE_X, "daily_run_asia.yml"),
  wd("twelve-x-london", "12 7 * * MON-FRI", TWELVE_X, "daily_run_london.yml"),
  // Weekday FX Hub clock; house-run-12 stays a disabled daily retry slot.
  wd("twelve-x-new-york", "17 12 * * MON-FRI", TWELVE_X, "daily_run_new_york.yml"),
  wd("twelve-x-market-context-intraday", "4 */4 * * *", TWELVE_X, "market_context_ingest.yml", {
    inputs: { bucket: "intraday" },
  }),
  wd("twelve-x-market-context-daily", "30 5 * * *", TWELVE_X, "market_context_ingest.yml", {
    inputs: { bucket: "daily" },
  }),
  wd("twelve-x-market-context-weekly", "8 7 * * SAT", TWELVE_X, "market_context_ingest.yml", {
    inputs: { bucket: "weekly" },
  }),
  wd("twelve-x-performance-eval", "30 17 * * MON-FRI", TWELVE_X, "performance_eval.yml"),
  wd(
    "twelve-x-primemarket-heartbeat",
    "3 6,18 * * *",
    TWELVE_X,
    "primemarket_session_heartbeat.yml",
  ),
  wd("twelve-x-session-catchup", "52 * * * MON-FRI", TWELVE_X, "session_catchup.yml"),
  // dry_run must be false: workflow defaults dispatch to dry_run=true and only
  // forced live on the old GHA schedule event. Pre-prune R2 dump stays on so the
  // transient market-context tables are always recoverable.
  wd("twelve-x-archive-maintenance", "30 2 * * *", TWELVE_X, "archive_maintenance.yml", {
    inputs: { dry_run: "false", dump_before_prune: "true" },
  }),
  // Prior GHA was `0 9 * * 1` (Mon 09:00 UTC). Minute :08 is the house off-grid
  // offset (same as twelve-x-market-context-weekly) and does not collide with
  // house-run-09 at 09:17 (`17 9 * * MON`) or project-enforce-assignment at 09:23.
  // days input omitted — workflow default 14.
  wd("twelve-x-digisearch-parity", "8 9 * * MON", TWELVE_X, "digisearch_parity_check.yml"),
];

/** Exact cron-string match; one trigger may map to multiple jobs. */
export function jobsForCron(
  cron: string,
  opts: { includeDisabled?: boolean } = {},
): Job[] {
  return JOBS.filter((j) => (opts.includeDisabled || j.enabled) && j.cron === cron);
}

/** Unique cron expressions for enabled jobs (wrangler [triggers] must match). */
export function uniqueEnabledCrons(): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const j of JOBS) {
    if (!j.enabled) continue;
    if (seen.has(j.cron)) continue;
    seen.add(j.cron);
    out.push(j.cron);
  }
  return out;
}
