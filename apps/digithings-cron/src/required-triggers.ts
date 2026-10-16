/**
 * The required-trigger contract (DIG-732, DIG-553 Finding 1).
 *
 * Finding 1, measured over 543 runs: 1-30 Aug 2026 produced zero session
 * catch-up runs, so every failed FX session that day stayed unrecovered. Six of
 * the twelve client-visible stale days (7, 14, 19, 20, 24, 25 Aug) fall before
 * 2026-08-31, the Worker's first clock day, and nothing at all reported them.
 *
 * The backstop existed only as a line in wrangler.toml. Deleting the
 * `twelve-x-session-catchup` job row and its cron line together left every
 * assertion in the repo green, because the only thing that noticed was a
 * hardcoded expected-id list in a unit test nobody ran for five weeks. A
 * missing trigger was a fact about a file, not an asserted control.
 *
 * This module is that control, as data. Each entry names a cron the FX pipeline
 * cannot run without, the job row that owns it, and **why it is required** — the
 * reason travels with the trigger so the alarm says what broke rather than
 * which line disappeared.
 *
 * The contract names the *capability* the pipeline requires. DIG-678 / DIG-55
 * own whether the catch-up is a GitHub workflow or a Cloudflare-native path; if
 * the row that satisfies a trigger here changes, change this file in the same
 * commit. What must never happen is the cron quietly disappearing — that is what
 * `src/trigger-contract.ts` fails on and `src/trigger-alarm.ts` raises.
 */

/** One cron the FX pipeline cannot run without. */
export type RequiredTrigger = {
  /** Job id that owns the cron. Resolved against JOBS by the contract check. */
  job: string;
  /** Cron expression that must appear in the deployed trigger list. */
  cron: string;
  /** Why the pipeline requires this trigger. Shown verbatim in the alarm body. */
  reason: string;
  /** What is lost while the trigger is absent. Named so the alarm states the cost. */
  lost: string;
  /** Linked finding, so an alarm reader can get the measurement, not a summary. */
  evidence: string;
};

/**
 * The required set. Order is the reading order: the three session clocks, then
 * the backstop that recovers them, then the beacon that reports them dead.
 */
export const REQUIRED_TRIGGERS: readonly RequiredTrigger[] = [
  {
    job: "twelve-x-asia",
    cron: "7 0 * * MON-FRI",
    reason: "The asia FX session's own clock. It starts daily_run_asia and nothing else does.",
    lost: "No asia research for the day, and no later clock will produce it.",
    evidence: "DIG-553 Finding 1",
  },
  {
    job: "twelve-x-london",
    cron: "12 7 * * MON-FRI",
    reason: "The london FX session's own clock. It starts daily_run_london and nothing else does.",
    lost: "No london research for the day, and no later clock will produce it.",
    evidence: "DIG-553 Finding 1",
  },
  {
    job: "twelve-x-new-york",
    cron: "17 12 * * MON-FRI",
    reason:
      "The new-york FX session clock, weekday only. It starts daily_run_new_york and nothing else does.",
    lost: "No new-york research for the day, and no later clock will produce it.",
    evidence: "DIG-553 Finding 1",
  },
  {
    job: "twelve-x-session-catchup",
    cron: "52 * * * MON-FRI",
    reason:
      "The hourly backstop. Each tick starts any fx-<session> run the session clocks above did not start, so a failed session becomes a later run instead of a stale day.",
    lost:
      "Every failed session day stays unrecovered. This is the exact 1-30 Aug 2026 gap: zero catch-up runs, six client-visible stale days nothing could recover.",
    evidence: "DIG-553 Finding 1, 543 runs",
  },
  {
    job: "twelve-x-primemarket-heartbeat",
    cron: "3 6,18 * * *",
    reason:
      "Twice-daily liveness beacon for the FX session window. It is how a dead session clock surfaces within a day instead of at the next client complaint.",
    lost: "A dead FX session stays invisible for days, which is how 1-30 Aug went unnoticed.",
    evidence: "DIG-553 Finding 1",
  },
];

/** Distinct crons required (dedup by expression; the job column may repeat). */
export function requiredCrons(): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const trigger of REQUIRED_TRIGGERS) {
    if (seen.has(trigger.cron)) continue;
    seen.add(trigger.cron);
    out.push(trigger.cron);
  }
  return out;
}