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
 *   unrecognised_cron     — a cron in the list under test maps to no enabled
 *                           job. It fires and does nothing. Drift, not loss.
 *
 * A deployed cron that is both is reported once, as missing: deleting the job
 * row and forgetting the cron line is one defect and must not raise two alarms.
 *
 * One third state exists so both layers read the same world: a cron whose only
 * owners are deliberately disabled job rows is *parked*. It is not drift, so
 * neither the contract nor the tick calls it unrecognised. The tick and the
 * contract therefore agree on parked, which they did not before DIG-732 review:
 * the contract rejected a disabled slot while the tick tolerated it.
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
 * Crons whose only owners are disabled job rows.
 *
 * `house-run-10/11/12` are the reason this exists: they keep their cron lines as
 * retry slots while the rows are switched off. A cron is parked only when no
 * enabled row claims it too — otherwise the enabled job is what is running it.
 */
function parkedCrons(jobs: readonly Job[]): Set<string> {
  const enabled = new Set<string>();
  const disabled = new Set<string>();
  for (const job of jobs) {
    (job.enabled ? enabled : disabled).add(normaliseCron(job.cron));
  }
  const parked = new Set<string>();
  for (const cron of disabled) {
    if (!enabled.has(cron)) parked.add(cron);
  }
  return parked;
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
  const mapped = new Set<string>();
  for (const job of jobs) {
    if (job.enabled) mapped.add(normaliseCron(job.cron));
  }
  const requiredCrons = new Set(required.map((trigger) => normaliseCron(trigger.cron)));
  const parked = parkedCrons(jobs);

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
    if (mapped.has(cron)) continue;
    // A required cron nobody claims is already reported as missing. Reporting it
    // again as unrecognised would turn one deletion into two alarms.
    if (requiredCrons.has(cron)) continue;
    // A cron only disabled rows claim is a known configuration, not drift. The
    // tick tolerates these too; see parkedCrons.
    if (parked.has(cron)) continue;
    unrecognised.push({
      class: UNRECOGNISED_CRON,
      cron,
      job: null,
      reason: `"${cron}" is in the trigger list under test and maps to no enabled job in src/jobs.ts, so it fires and starts nothing`,
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
    reason: `"${cron}" fired and maps to no enabled job in src/jobs.ts, so the tick did nothing`,
    lost: "whatever that trigger used to run, at whatever rate it used to run",
    evidence: "DIG-732",
  };
}

/**
 * The violations a firing cron raises, derived from the same contract.
 *
 * The tick cannot call `checkTriggerContract([cron])`: the cron is firing, so it
 * is by definition in the list, and the question is only whether an enabled job
 * is behind it. Asking that question through the contract is what stops the two
 * layers from disagreeing about the same world — the review found a disabled
 * *required* row reported as missing by the contract and as silence by the tick.
 *
 *   enabled owner      → no violation; the tick has a job
 *   parked (disabled)  → no violation; a known configuration
 *   required cron      → missing_required_cron; it fires with no backstop
 *   anything else      → unrecognised_cron; it fires with nothing behind it
 */
export function violationsForTick(
  cron: string,
  opts: { jobs?: readonly Job[]; required?: readonly RequiredTrigger[] } = {},
): TriggerViolation[] {
  const jobs = opts.jobs ?? JOBS;
  const required = opts.required ?? REQUIRED_TRIGGERS;
  const firing = normaliseCron(cron);
  const enabledOwns = jobs.some((job) => job.enabled && normaliseCron(job.cron) === firing);
  if (enabledOwns) return [];
  if (parkedCrons(jobs).has(firing)) return [];
  const trigger = required.find((row) => normaliseCron(row.cron) === firing);
  if (trigger) {
    const job = jobs.find((row) => row.id === trigger.job);
    return [
      {
        class: MISSING_REQUIRED_CRON,
        cron: trigger.cron,
        job: trigger.job,
        reason: `${trigger.reason} (it fired, but ${missingReason(trigger, job)})`,
        lost: trigger.lost,
        evidence: trigger.evidence,
      },
    ];
  }
  return [unrecognisedCronViolation(cron)];
}

/** Human-readable one line per violation. Used by scripts and test failures. */
export function describeVerdict(verdict: TriggerContractVerdict, source: string): string[] {
  if (verdict.ok) return [`trigger contract satisfied against ${source} (${verdict.present} crons)`];
  return verdict.violations.map(
    (violation) =>
      `${violation.class}: ${violation.cron}${violation.job ? ` (${violation.job})` : ""} — ${violation.reason}`,
  );
}