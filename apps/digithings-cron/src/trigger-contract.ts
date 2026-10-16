/**
 * The required-trigger contract check (DIG-732).
 *
 * Pure: it takes a trigger list and a job list and returns a verdict. It never
 * learns whether that list came from `wrangler.toml` or from the deployed
 * Worker's schedule API, because the answer must not depend on the source. A
 * contract satisfied by the repo but not by the deployment is Finding 1 wearing
 * a passing test.
 *
 * Two classes, and they are deliberately not the same thing:
 *
 *   missing_required_cron — a cron the FX pipeline requires is not in the list
 *                           under test, or the job row that owns it is gone,
 *                           disabled, or pointing somewhere else. Data is lost.
 *   unrecognised_cron     — a cron in the list under test is claimed by no job
 *                           row at all, not even a disabled one. It fires and
 *                           does nothing. Drift, not loss. A cron whose only
 *                           owner is a disabled job is a known configuration and
 *                           is recognised, not unrecognised, so this check agrees
 *                           with the tick in `src/index.ts` on that point.
 *
 * A deployed cron that is both is reported once, as missing: deleting the job
 * row and forgetting the cron line is one defect and must not raise two alarms.
 */
import { JOBS, type Job } from "./jobs";
import { REQUIRED_TRIGGERS, type RequiredTrigger } from "./required-triggers";

export const MISSING_REQUIRED_CRON = "missing_required_cron";
export const UNRECOGNISED_CRON = "unrecognised_cron";

export type AlarmClass = typeof MISSING_REQUIRED_CRON | typeof UNRECOGNISED_CRON;

/** One way the trigger list fails its contract, already carrying the reason. */
export type TriggerViolation = {
  class: AlarmClass;
  cron: string;
  /** The required job that owns the cron, or null for an unrecognised cron. */
  job: string | null;
  /** Why the trigger is required, plus what is wrong with this one. */
  reason: string;
  /** What is lost while the trigger is absent. */
  lost: string;
  /** The finding that makes this a control rather than an opinion. */
  evidence: string;
};

export type TriggerContractVerdict = {
  /** True only when both classes are empty. */
  ok: boolean;
  /** How many distinct cron expressions the list under test holds. */
  present: number;
  missing: TriggerViolation[];
  unrecognised: TriggerViolation[];
  /** Every violation, missing first. One alarm per class is derived from this. */
  violations: TriggerViolation[];
};

function normaliseCron(cron: string): string {
  return cron.trim().replace(/\s+/g, " ");
}

function missingReason(trigger: RequiredTrigger, job: Job | undefined): string {
  if (!job) return `no job row in src/jobs.ts owns ${trigger.job}`;
  if (!job.enabled) return `the job row for ${trigger.job} is disabled`;
  if (normaliseCron(job.cron) !== normaliseCron(trigger.cron)) {
    return `the job row for ${trigger.job} now runs "${job.cron}" instead of "${trigger.cron}"`;
  }
  return "";
}

/**
 * Evaluate the contract against a trigger list.
 *
 * `crons` is the list under test: the deployed schedule list in production, or
 * the `[triggers].crons` list before a deploy, or a fixture in a test. The
 * defaults are the live job map and the live contract, so a caller that wants to
 * prove a deletion can pass the mutated world and keep the contract fixed.
 */
export function checkTriggerContract(
  crons: readonly string[],
  opts: { jobs?: readonly Job[]; required?: readonly RequiredTrigger[] } = {},
): TriggerContractVerdict {
  const jobs = opts.jobs ?? JOBS;
  const required = opts.required ?? REQUIRED_TRIGGERS;
  const deployed = new Set<string>();
  for (const cron of crons) {
    const normalised = normaliseCron(cron);
    if (normalised.length > 0) deployed.add(normalised);
  }
  // A cron whose only owner is a deliberately disabled job (`house-run-10/11/12`
  // keep their cron lines as retry slots) is a known configuration, not drift:
  // `src/index.ts` deliberately stays quiet for it at the tick, and this check
  // has to agree. Requiring an *enabled* owner here would red the deploy and
  // open an issue for a slot the tick path treats as correct. A required cron
  // is unaffected — it is checked above, and `missingReason` is what notices
  // that its job row is disabled or points elsewhere.
  const claimed = new Set<string>();
  for (const job of jobs) {
    claimed.add(normaliseCron(job.cron));
  }
  const requiredCrons = new Set(required.map((trigger) => normaliseCron(trigger.cron)));

  const missing: TriggerViolation[] = [];
  for (const trigger of required) {
    const job = jobs.find((row) => row.id === trigger.job);
    const inList = deployed.has(normaliseCron(trigger.cron));
    const wrong = missingReason(trigger, job);
    if (inList && wrong === "") continue;
    const detail = inList
      ? wrong
      : `"${trigger.cron}" is absent from the trigger list under test`;
    missing.push({
      class: MISSING_REQUIRED_CRON,
      cron: trigger.cron,
      job: trigger.job,
      reason: `${trigger.reason} (${detail})`,
      lost: trigger.lost,
      evidence: trigger.evidence,
    });
  }

  const unrecognised: TriggerViolation[] = [];
  for (const cron of deployed) {
    if (claimed.has(cron)) continue;
    // A required cron nobody claims is already reported as missing. Reporting it
    // again as unrecognised would turn one deletion into two alarms.
    if (requiredCrons.has(cron)) continue;
    unrecognised.push({
      class: UNRECOGNISED_CRON,
      cron,
      job: null,
      reason: `"${cron}" is in the trigger list under test and no job row in src/jobs.ts claims it, not even a disabled one, so it fires and starts nothing`,
      lost: "whatever that trigger used to run, at whatever rate it used to run",
      evidence: "DIG-732",
    });
  }

  return {
    ok: missing.length === 0 && unrecognised.length === 0,
    present: deployed.size,
    missing,
    unrecognised,
    violations: [...missing, ...unrecognised],
  };
}

/** The violation a cron trigger raises when it fires with no job behind it. */
export function unrecognisedCronViolation(cron: string): TriggerViolation {
  return {
    class: UNRECOGNISED_CRON,
    cron,
    job: null,
    reason: `"${cron}" fired and no job row in src/jobs.ts claims it, not even a disabled one, so it started nothing`,
    lost: "whatever that trigger used to run, at whatever rate it used to run",
    evidence: "DIG-732",
  };
}

/** Human-readable one line per violation. Used by scripts and test failures. */
export function describeVerdict(verdict: TriggerContractVerdict, source: string): string[] {
  if (verdict.ok) {
    const count = verdict.present;
    return [`trigger contract satisfied against ${source} (${count} ${count === 1 ? "cron" : "crons"})`];
  }
  return verdict.violations.map(
    (violation) =>
      `${violation.class}: ${violation.cron}${violation.job ? ` (${violation.job})` : ""} — ${violation.reason}`,
  );
}