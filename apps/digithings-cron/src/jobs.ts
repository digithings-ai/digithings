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
  /**
   * Input keys of which at least one must carry a non-empty value (static
   * inputs plus per-request `/kick` args) before this row may be dispatched.
   * Unset means no requirement. Enforced in dispatchGithub BEFORE any dispatch,
   * dry-run or real, so a refusal never reaches api.github.com.
   */
  requiredKickArgs?: readonly string[];
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
    requiredKickArgs?: readonly string[];
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
    requiredKickArgs: opts.requiredKickArgs,
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

  // --- twelve-x (FX Hub) — resumed 2026-10-01 (Human Gate unlock) ---
  // digisearch_parity is not a digithings workflow (leftover sweep after #4970).
  // Add a CLOCK-DRIVEN twelve-x wd() row only with a known cron from that
  // repo. A manual-only row (shipped switched off, addressed by cron string
  // through POST /kick) is the one exception; see twelve-x-snapshot-backfill.
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
  /**
   * Manual-only sanctioned trigger for dated snapshot backfills.
   *
   * Why this row exists: the FX session pipeline moved to the digiquant-runner
   * clocks, so twelve-x's `maintenance.yml` lost its schedule and is
   * `disabled_manually` on GitHub. Remediation therefore has no SSOT path —
   * only an operator clicking "Run workflow" in the GitHub UI, which bypasses
   * every Worker audit line. This row is the auditable equivalent.
   *
   * The row ships switched off, and that is load-bearing, not provisional:
   *  - `uniqueEnabledCrons()` skips a switched-off row, so it is absent from
   *    wrangler.toml `[triggers]` and Cloudflare can never fire it. No clock
   *    exists.
   *  - `0 0 30 2 *` is a sentinel that can never match: 30 February does not
   *    occur. If someone later switches the row on without adding a real
   *    trigger, it still does not fire.
   *  - `POST /kick` passes `includeDisabled: true`, which is the only way to
   *    reach it. Same mechanism the switched-off `house-run-10/11/12` rows
   *    use.
   *
   * Clock-rule compatibility: the rule above this block ("add a twelve-x
   * `wd()` row only with a known cron from that repo") governs rows a CLOCK
   * drives. This row has no clock by design, so there is no cron to know — the
   * sentinel exists purely so the row is addressable by `/kick`. Adding it does
   * not put an unsourced cron on the org's clock.
   *
   * Editing this comment: `tests/scripts/test_prices_cron_dst.py` reads this
   * file as text, not as a module. It takes everything between one row call
   * and the next, and drops a row when that span contains the switch-off
   * marker it greps for. Comment text in that span is attributed to the row
   * ABOVE, so spelling the marker out anywhere in this block would drop
   * `twelve-x-digisearch-parity` from the clock set and fail the parity test.
   * The option object below is the only place the marker may appear. (DIG-55
   * hit exactly that failure: see PR #5055.)
   *
   * `ref` is `develop` via `wd()`. Safe only while the reviewed blob shas
   * match between branches; verified at DIG-55 time:
   *   nodes/snapshot_publish.py    develop == main == 66ee88ae
   *   scripts/backfill_snapshots.py develop == main == 8e65ffd8
   * Re-verify both before switching the row on, and prefer flipping it on
   * `main` if they ever diverge.
   *
   * Static inputs are deliberately just `{ backfill_snapshots: "true" }`:
   *  - It is a subset of what twelve-x `develop` declares today, so this row
   *    never 422s on an unexpected key. `dates` and `until` only exist after
   *    twelve-x#237 merges, and they travel as per-request `/kick` args.
   *  - There is NO date bound in configuration, and that is now enforced, not
   *    just documented. `maintenance.yml` treats an empty `since` as "from the
   *    beginning": it only passes `--since` when the input is non-empty, and
   *    `backfill_snapshots.py` then keeps EVERY distinct stored run_date and
   *    re-projects each one with a fresh `as_of=now`. That rewrites
   *    fx_consensus_snapshot (both views), fx_confluence_snapshot and
   *    fx_events_snapshot for the whole history, and each `_upsert` then prunes
   *    any older generation for that run_date. `requiredKickArgs` below makes
   *    the row REFUSE a kick that carries none of since/dates/until, before any
   *    dispatch. The GitHub UI still has the same exposure; this row no longer
   *    walks into it.
   *  - The bound must be zero-padded ISO (`2026-06-02`, never `2026-6-2`):
   *    the bounds compare as strings, so an unpadded month sorts after every
   *    stored run_date and silently re-stamps the whole table.
   *
   * ORDERING GATE — read before using this row. This row is build-complete
   * here, but one-date-per-dispatch is not usable until twelve-x#237 (DIG-52)
   * merges. Today twelve-x `develop` declares only `backfill_snapshots` and
   * `since`, and `since` is a LOWER bound with no upper bound:
   * `backfill_snapshots.py` filters `d >= since`, so `since=2026-06-02`
   * re-projects every stored run_date from that date to now, each with a fresh
   * `as_of=now`. That is a bounded-from forward sweep, NOT one date. Until #237
   * lands, an operator using `since` must accept that sweep; the one-date
   * remediation sequence needs #237. Do not add a `dates` key here before #237
   * — it is not a declared input yet and would 422.
   *
   * Prune safety: this path can never prune `fx_trade_ideas_snapshot`. That
   * table is only written by the live FX session pipeline, which passes
   * `trade_ideas`; `maintenance.yml` reaches `project_snapshots` with
   * `trade_ideas=None`, so the trade-ideas `_upsert` returns on empty rows
   * before its `_prune`. `dispatch.test.ts` pins the Worker-side half: this row
   * declares no input outside the set twelve-x `maintenance.yml` declares. The
   * runtime half is written in twelve-x `tests/test_backfill_snapshots.py`
   * (`test_trade_ideas_snapshot_is_never_written_or_pruned`) and lands with
   * twelve-x#237 (DIG-52); it is NOT in `test_snapshot_publish.py`.
   *
   * Blast radius of per-request `/kick` args — known and accepted. The same
   * `dispatchGithub` merge applies to EVERY workflow_dispatch row, so a `/kick`
   * carrying `args` can also override a row's own static inputs (`dry_run` on
   * agent-pr-finalizer, `bucket` on the market-context rows). Precedence is
   * `{ ...(job.inputs ?? {}), ...args }` — args win — because that is the
   * contract recorded for DIG-69/DIG-73 (`start_key` must be able to add a key
   * to a row). Bounds: `/kick` requires `CRON_KICK_SECRET`, and every
   * `inputs.*` in the workflows is bound through `env:`, never interpolated
   * into a `run:` line, so this is a surface widening rather than injection.
   */
  wd(
    "twelve-x-snapshot-backfill",
    "0 0 30 2 *",
    TWELVE_X,
    "maintenance.yml",
    {
      inputs: { backfill_snapshots: "true" },
      enabled: false,
      // Refuse a kick with no date bound — see the backfill-sweep bullet above.
      // `dates` and `until` are listed so this survives twelve-x#237 (DIG-52)
      // merging; today only `since` is a declared input and the other two would
      // 422 at GitHub anyway, so naming them cannot loosen the guard.
      requiredKickArgs: ["since", "dates", "until"],
    },
  ),
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
