/**
 * Typed job map for digithings-cron.
 * Each enabled job.cron must appear in wrangler.toml [triggers] crons.
 */
export type JobKind =
  | "workflow_dispatch"
  | "repository_dispatch"
  | "container"
  | "probe"
  | "watch"
  | "twelvex-watch";

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
  /**
   * Set when kind is "watch". The service this job only READS. There is no
   * `command`: a watch job has nothing to start, and nothing to time out. Its
   * job is to notice a run the runner is still holding open. It never POSTs to
   * /v1/jobs — see house-run-watch.ts.
   */
  watch?: "digiquant-runner";
  /** Set when kind is "twelvex-watch". Worker-only read of twelve-x Actions history. */
  twelvexWatch?: "feed-confirm" | "primemarket-heartbeat";
  /**
   * Worker-side pre-check before a workflow_dispatch. "twelvex-session-due" skips
   * session_catchup.yml when no session can be due (see twelvex-watch.ts).
   * A forced kick bypasses the gate.
   */
  gate?: "twelvex-session-due";
};

const MONOREPO = "digithings-ai/digithings" as const;
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
    repo: MONOREPO,
    kind: "probe",
    workflow,
    ref: DEVELOP,
    enabled: opts.enabled ?? true,
    probe,
  };
}

/**
 * Watch job (DIG-3065). Read-only against the named service.
 *
 * `workflow` and `ref` stay, for the same reason they stay on `pj`/`cj`:
 * GITHUB_OVERRIDE_JOBS can still redirect the id to a workflow dispatch, and
 * `jobs.test.ts` asserts `ref === "develop"` on every non-repository_dispatch
 * row. The watcher itself never uses either — it resolves its deadline from the
 * house-run row via houseRunDeadlineSeconds(), so there is no second copy of
 * 14400 to drift.
 */
function wj(id: string, cron: string, watch: "digiquant-runner", opts: { enabled?: boolean } = {}): Job {
  return {
    id,
    cron,
    repo: MONOREPO,
    kind: "watch",
    workflow: "pipeline-digiquant.yml",
    ref: DEVELOP,
    enabled: opts.enabled ?? true,
    watch,
  };
}

/**
 * twelve-x watchdog run in this Worker (no GitHub runner). workflow + ref stay so
 * GITHUB_OVERRIDE_JOBS can fall back to the original GHA watchdog workflow.
 */
function tw(
  id: string,
  cron: string,
  workflow: string,
  twelvexWatch: "feed-confirm" | "primemarket-heartbeat",
): Job {
  return { id, cron, repo: TWELVE_X, kind: "twelvex-watch", workflow, ref: DEVELOP, enabled: true, twelvexWatch };
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
    repo: MONOREPO,
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
  wd("continuous-improvement", "8 22 * * SUN", MONOREPO, "pipeline-continuous-improvement.yml"),
  wd("maintenance", "8 8 * * MON", MONOREPO, "pipeline-maintenance.yml"),
  wd("provider-review", "9 0 * * SUN", MONOREPO, "pipeline-provider-review.yml"),

  // --- digithings: ops / agent / smoke (off-grid minutes) ---
  // Path A traps restored after #4967 (Approve-full). YAML is workflow_dispatch
  // only; clocks live here. dry_run must be false: workflow defaults dispatch
  // to dry_run=true and only forced live on the old GHA schedule event.
  wd("agent-pr-finalizer", "11 7 * * *", MONOREPO, "agent-pr-finalizer.yml", {
    inputs: { dry_run: "false" },
  }),
  wd("agent-backlog-snapshot", "13 6 * * MON", MONOREPO, "agent-backlog-snapshot.yml"),
  wd("ci-pr-hygiene", "21 6 * * *", MONOREPO, "ci-pr-hygiene.yml"),
  wd("refresh-repo-activity", "10 6 * * MON", MONOREPO, "refresh-repo-activity.yml"),
  wd(
    "project-enforce-assignment",
    "23 9 * * *",
    MONOREPO,
    "project-enforce-assignment.yml",
  ),
  pj("smoke-stack", "27 7 * * *", "smoke-stack.yml", "stack"),
  wd("security-pip-audit", "33 6 * * MON", MONOREPO, "security-pip-audit.yml"),
  wd("security-npm-audit", "37 6 * * MON", MONOREPO, "security-npm-audit.yml"),
  // Daily, not weekly: an expired credential should surface in <=24h, which is
  // the point of the canary (#3522).
  wd("token-canary", "41 6 * * *", MONOREPO, "token-canary.yml"),
  // Ported from main's GitHub schedule (Oct 2026 release). Weekly OpenWiki refresh.
  wd("openwiki-update", "0 8 * * MON", MONOREPO, "openwiki-update.yml"),
  // Ported from main's GitHub schedule. Alerts when a production deployment waits
  // on the environment gate too long (DIG-1569); every 30 minutes.
  wd(
    "production-deploy-gate-watchdog",
    "17,47 * * * *",
    MONOREPO,
    "production-deploy-gate-watchdog.yml",
  ),
  // Monthly environment-gate drift check (#248). NOT an ageing sweep: DIG-477
  // option D (Chris, 2026-10-05) took the secret ageing out of this job, because the
  // Actions secrets endpoints need a token with the `repo` scope that a workflow's
  // GITHUB_TOKEN never has. Do not call this an ageing sweep in a comment; that
  // exact claim is what DIG-477 retracted. Ageing runs by hand via
  // `make secrets-staleness`, tracked monthly as Paperclip DIG-668.
  // The clock lives here and not on the workflow: develop carries no on.schedule, and
  // the workflow is workflow_dispatch only. Off :00 and off the smoke-site minute
  // so nothing lands on a shared runner's worst moment.
  wd("secret-staleness", "17 6 1 * *", MONOREPO, "secret-staleness-check.yml"),
  // Monthly uv.lock-vs-PyPI version radar (DIG-1515). This monorepo's floors are
  // `>=`, so the floor is not what runs: the lock already sits majors past several
  // stated floors with nobody having approved the jump. This makes that gap visible
  // on purpose instead of mid-incident. Read-only, it changes no bound.
  // The clock lives here and not on the workflow, for the same reason as the row
  // above: develop carries no on.schedule, and the workflow is workflow_dispatch
  // only. Off :17 so it never shares a runner minute with the monthly sweep.
  wd("dependency-freshness", "23 6 1 * *", MONOREPO, "pipeline-dependency-freshness.yml"),
  pj("smoke-site", "17 6 * * *", "smoke-site.yml", "site"),
  // Hourly answer-integrity probe against DataTap production. Clock lives here,
  // not on the workflow: develop carries no on.schedule (#DIG-306). Read-only.
  wd("datatap-answer-check", "17 * * * *", MONOREPO, "datatap-answer-check.yml"),

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
  // Gated in the Worker: most hourly ticks found nothing due and still billed a
  // private-repo Actions job. The gate only skips when every due slot is covered.
  {
    ...wd("twelve-x-session-catchup", "52 * * * MON-FRI", TWELVE_X, "session_catchup.yml"),
    gate: "twelvex-session-due",
  },
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

  // --- twelve-x: feed-published confirmation, and the watchdog for the watchdog --
  //
  // DIG-1073. The confirmation itself already exists in twelve-x
  // (scripts/confirm_feed_published.py) and already has the exit-code contract
  // DIG-1073 asked for: 0 clean, 1 gaps, 2 could-not-run. What it lacked was a
  // clock of its own. Its only clock was a Paperclip routine, and a routine
  // opens a run *assigned to an agent* — so when that run died, the day was
  // simply unreported. It died on the first day: run 69d54f36 was
  // `adapter_failed: Rate limit exceeded` and nothing alerted. That is DIG-526
  // again (a detector failing 29 consecutive times over 14 days, alerting
  // nobody), so detection must not live in the agent loop.
  //
  // So: the clock lives here, in the Worker, and the Worker's only job is to
  // dispatch. The check runs in Actions because that is where
  // TWELVEX_SUPABASE_SERVICE_KEY already exists — no new credential to
  // provision (DIG-377 tracked the equivalent for the Worker, and this route
  // does not need it).
  //
  // Weekday-only, matching the FX session clocks it reads: the check's
  // expected-date rule is the weekday rule, so a weekend firing would report a
  // gap that is not one.
  //
  // 14:41Z is 2h24m after twelve-x-new-york (12:17Z): late enough that the
  // new-york session has had time to publish, early enough to leave room for
  // the watchdog below.
  wd("twelve-x-feed-confirm", "41 14 * * MON-FRI", TWELVE_X, "feed_published_confirm.yml"),

  // The watchdog exists because "the check said pass" and "the check did not
  // run" are otherwise indistinguishable from the outside — which is the whole
  // point of DIG-1073. It asks a *different* workflow whether that workflow
  // completed, and pages if it did not. 16:23Z is 1h42m after the confirm, far
  // inside the watchdog's 6h lookback, so ordinary Actions queueing cannot make
  // a healthy day look silent. Gap to the next confirm is ~22h, so a confirm
  // missed outright is caught the same day, not the next morning.
  // Runs in this Worker now (twelvex-watch.ts); GITHUB_OVERRIDE_JOBS falls back to GHA.
  tw("twelve-x-feed-confirm-watchdog", "23 16 * * MON-FRI", "feed_confirm_watchdog.yml", "feed-confirm"),
  // Hourly lost-house-run watcher (DIG-3065). Appended last so the deploy-config
  // contract, which compares wrangler.toml [triggers].crons to uniqueEnabledCrons()
  // in order, needs no reshuffle. Minute :23 is clear of the :17 cluster
  // (production-deploy-gate-watchdog, datatap-answer-check, smoke-site), :41
  // (token-canary) and :47, and clear of the 09:17 house-run start it watches.
  wj("digiquant-house-run-watch", "23 * * * *", "digiquant-runner"),
  // Was the GHA `schedule: 40 */6 * * *` on primarketet_heartbeat_watchdog.yml.
  tw(
    "twelve-x-primemarket-heartbeat-watchdog",
    "40 */6 * * *",
    "primarketet_heartbeat_watchdog.yml",
    "primemarket-heartbeat",
  ),
];

/**
 * The timeout_seconds the house-run watcher applies to a run the runner still
 * reports open (DIG-3065).
 *
 * Resolved from the house-run job row rather than written into the watcher, so
 * 14400 has exactly one home: changing house-run-09's timeout moves the
 * deadline with it, and a test can assert the two agree instead of asserting a
 * copied literal. `undefined` means the row is gone or unnamed — the watcher
 * then refuses to evaluate rather than guessing a deadline.
 */
export function houseRunDeadlineSeconds(from: readonly Job[] = JOBS): number | undefined {
  return from.find((job) => job.id === "house-run-09")?.timeoutSeconds;
}

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
