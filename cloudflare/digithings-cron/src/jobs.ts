/**
 * Typed job map for digithings-cron.
 * Each enabled job.cron must appear in wrangler.toml [triggers] crons.
 */
export type Job = {
  id: string;
  cron: string;
  repo: "digithings-ai/digithings" | "digithings-ai/twelve-x";
  kind: "workflow_dispatch" | "repository_dispatch";
  workflow?: string;
  inputs?: Record<string, string>;
  event_type?: string;
  ref?: "develop" | "main";
  etOpenGate?: boolean;
  enabled: boolean;
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

function rd(
  id: string,
  cron: string,
  repo: Job["repo"],
  event_type: string,
  opts: { enabled?: boolean } = {},
): Job {
  return {
    id,
    cron,
    repo,
    kind: "repository_dispatch",
    event_type,
    enabled: opts.enabled ?? true,
  };
}

/** All org production clocks. Source of truth alongside wrangler [triggers]. */
export const JOBS: readonly Job[] = [
  // --- digithings: digiquant prices ---
  wd("prices-at-open-13", "40 13 * * MON-FRI", DIGITHINGS, "pipeline-digiquant-prices.yml", {
    inputs: { mode: "at-open" },
    etOpenGate: true,
  }),
  wd("prices-at-open-14", "40 14 * * MON-FRI", DIGITHINGS, "pipeline-digiquant-prices.yml", {
    inputs: { mode: "at-open" },
    etOpenGate: true,
  }),
  wd(
    "prices-intraday",
    "7,22,37,52 13-21 * * MON-FRI",
    DIGITHINGS,
    "pipeline-digiquant-prices.yml",
    { inputs: { mode: "intraday" } },
  ),
  wd("prices-fx-refresh", "19 */2 * * MON-FRI", DIGITHINGS, "pipeline-digiquant-prices.yml", {
    inputs: { mode: "fx-refresh" },
  }),
  wd("prices-fx-refresh-sun", "19 22 * * SUN", DIGITHINGS, "pipeline-digiquant-prices.yml", {
    inputs: { mode: "fx-refresh" },
  }),
  wd("prices-eod-macro", "27 21 * * MON-FRI", DIGITHINGS, "pipeline-digiquant-prices.yml", {
    inputs: { mode: "eod-macro" },
  }),

  // --- digithings: house-run via repository_dispatch digiquant-baseline ---
  // Research/portfolio retries run every day; ordinary source cadence decides
  // refresh. Manual workflow_dispatch still owns explicit refresh_scope.
  rd("house-run-09", "17 9 * * *", DIGITHINGS, "digiquant-baseline"),
  rd("house-run-10", "17 10 * * *", DIGITHINGS, "digiquant-baseline"),
  rd("house-run-11", "17 11 * * *", DIGITHINGS, "digiquant-baseline"),
  rd("house-run-12", "17 12 * * *", DIGITHINGS, "digiquant-baseline"),

  wd("research-metrics", "5 22 * * *", DIGITHINGS, "pipeline-research-metrics.yml"),
  wd("tearsheets", "12 0 * * *", DIGITHINGS, "pipeline-digiquant-tearsheets.yml"),
  wd("onchain", "40 22 * * *", DIGITHINGS, "pipeline-digiquant-onchain.yml"),
  wd("execution-cron-check", "15 12 * * *", DIGITHINGS, "execution-cron-check.yml"),

  // --- digithings: ops / agent / smoke (off-grid minutes) ---
  wd(
    "continuous-improvement",
    "8 22 * * SUN",
    DIGITHINGS,
    "pipeline-continuous-improvement.yml",
  ),
  wd("maintenance", "8 8 * * MON", DIGITHINGS, "pipeline-maintenance.yml"),
  wd("provider-review", "9 0 * * SUN", DIGITHINGS, "pipeline-provider-review.yml"),
  // dry_run must be false: workflow defaults dispatch to dry_run=true and only
  // forced live on the old GHA schedule event.
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
  wd("smoke-stack", "27 7 * * *", DIGITHINGS, "smoke-stack.yml"),
  wd("security-pip-audit", "33 6 * * MON", DIGITHINGS, "security-pip-audit.yml"),
  wd("smoke-site", "17 6 * * *", DIGITHINGS, "smoke-site.yml"),

  // --- twelve-x (FX Hub); schedule removal is a follow-up in that repo ---
  wd("twelve-x-asia", "7 0 * * MON-FRI", TWELVE_X, "daily_run_asia.yml"),
  wd("twelve-x-london", "12 7 * * MON-FRI", TWELVE_X, "daily_run_london.yml"),
  // Weekday FX Hub clock; house-run-12 is daily (`17 12 * * *`) and separate.
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
];

/** Exact cron-string match; one trigger may map to multiple jobs. */
export function jobsForCron(cron: string): Job[] {
  return JOBS.filter((j) => j.enabled && j.cron === cron);
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
