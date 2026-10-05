/**
 * The required-trigger contract for digithings-cron (DIG-732, DIG-553 Finding 1).
 *
 * The FX pipeline's clocks are a control, not a comment in a TOML file. Before
 * this module, deleting a job row AND its cron line together was invisible:
 * `uniqueEnabledCrons()` derives the trigger set from the job rows, so removing
 * both sides of the pair left every assertion green. That is exactly how twelve-x
 * ran 1-30 August 2026 with zero catch-up runs and nothing said so.
 *
 * So the requirement is stated here, once, as data, with the reason each cron is
 * required. `evaluateTriggerContract` compares that data against a trigger list —
 * the DEPLOYED list when one is supplied, the repo's `wrangler.toml` otherwise —
 * and reports two faults that must never be collapsed into one:
 *
 *   required_cron_absent — a cron the FX pipeline needs is not in the trigger
 *                          list. Nothing will fire it. This is the DIG-553 gap.
 *   unmapped_cron        — a cron is in the trigger list that no enabled job
 *                          claims. Work is firing that nobody designed.
 *
 * The first loses cover. The second wastes it. Both are alarms, and they read
 * differently on purpose.
 */
import { uniqueEnabledCrons } from "./jobs";

export type RequiredTrigger = {
  /** Job id the trigger is required to reach. */
  readonly job: string;
  /** Cron expression, exactly as wrangler.toml and Cloudflare both spell it. */
  readonly cron: string;
  /** Why the FX pipeline breaks without this trigger. Shown in the alarm. */
  readonly reason: string;
};

/**
 * The explicit set of crons the FX pipeline requires.
 *
 * Scope is the FX session pipeline only, not every org clock: these are the
 * triggers whose absence is client-visible stale FX data. A clock that is
 * merely *important* still belongs in wrangler.toml alone; promoting it here
 * makes the contract a list of everything, which asserts nothing. If a clock
 * can leave a client looking at yesterday's number, it belongs here.
 */
export const REQUIRED_TRIGGERS: readonly RequiredTrigger[] = [
  {
    job: "twelve-x-asia",
    cron: "7 0 * * MON-FRI",
    reason:
      "FX desk session, Asia. Without it the first FX session of the day never " +
      "prices, and every later session inherits a stale book.",
  },
  {
    job: "twelve-x-london",
    cron: "12 7 * * MON-FRI",
    reason:
      "FX desk session, London. Without it the London open is unpriced and the " +
      "Asia session carries stale data into the London handoff.",
  },
  {
    job: "twelve-x-new-york",
    cron: "17 12 * * MON-FRI",
    reason:
      "FX desk session, New York, the last session of the desk day. Without it " +
      "the closing FX fix for the whole day never lands.",
  },
  {
    job: "twelve-x-session-catchup",
    cron: "52 * * * MON-FRI",
    reason:
      "The hourly backstop that recovers a failed session. Without it a single " +
      "failed run is unrecoverable until a human notices. Zero catch-up runs ran " +
      "in 1-30 August 2026 and no control said so (DIG-553 Finding 1, 543 runs).",
  },
  {
    job: "twelve-x-primemarket-heartbeat",
    cron: "3 6,18 * * *",
    reason:
      "Twice-daily desk-session expiry check. Without it an expired " +
      "PRIMEMARKET_SESSION_TOKEN keeps every session failing silently for a day.",
  },
] as const;

/** Alarm class: a required cron is not in the trigger list. Cover is lost. */
export const REQUIRED_CRON_ABSENT = "required_cron_absent";
/** Alarm class: the trigger list holds a cron no enabled job claims. */
export const UNMAPPED_CRON = "unmapped_cron";

export type AlarmClass = typeof REQUIRED_CRON_ABSENT | typeof UNMAPPED_CRON;

export type TriggerContractViolation =
  | {
      readonly alarm_class: typeof REQUIRED_CRON_ABSENT;
      readonly cron: string;
      readonly job: string;
      readonly reason: string;
    }
  | {
      readonly alarm_class: typeof UNMAPPED_CRON;
      readonly cron: string;
    };

export type TriggerContractResult = {
  /** True when the trigger list satisfies the contract. */
  readonly ok: boolean;
  /** How many required triggers were looked for. */
  readonly checked: number;
  readonly violations: readonly TriggerContractViolation[];
};

/**
 * Compare the required-trigger contract against a trigger list.
 *
 * `deployedCrons` is whatever the caller can actually observe: the Cloudflare
 * schedules API in CI, `wrangler.toml` locally. `mappedCrons` defaults to the
 * crons of the enabled jobs, which is precisely the set `runJobsForCron` can
 * dispatch — so a cron outside it is a cron that would log `unmapped_cron` when
 * it fires.
 */
export function evaluateTriggerContract(
  deployedCrons: readonly string[],
  opts: { mappedCrons?: readonly string[] } = {},
): TriggerContractResult {
  const mapped = new Set(opts.mappedCrons ?? uniqueEnabledCrons());
  const deployed = new Set(deployedCrons);
  const violations: TriggerContractViolation[] = [];

  for (const trigger of REQUIRED_TRIGGERS) {
    if (!deployed.has(trigger.cron)) {
      violations.push({
        alarm_class: REQUIRED_CRON_ABSENT,
        cron: trigger.cron,
        job: trigger.job,
        reason: trigger.reason,
      });
    }
  }

  for (const cron of deployedCrons) {
    if (!mapped.has(cron)) {
      violations.push({ alarm_class: UNMAPPED_CRON, cron });
    }
  }

  return { ok: violations.length === 0, checked: REQUIRED_TRIGGERS.length, violations };
}

/**
 * Contract rows no enabled job claims.
 *
 * This is a bug in the contract itself rather than in a deployment, so it is
 * kept separate from `evaluateTriggerContract`: a contract that names a cron
 * nothing dispatches would otherwise pass forever while claiming cover it does
 * not have.
 */
export function contractGaps(
  mappedCrons: readonly string[] = uniqueEnabledCrons(),
): RequiredTrigger[] {
  const mapped = new Set(mappedCrons);
  return REQUIRED_TRIGGERS.filter((trigger) => !mapped.has(trigger.cron));
}

/** Strip a `#` comment that is not inside a quoted string. */
function stripComment(line: string): string {
  let inString = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') inString = !inString;
    else if (ch === "#" && !inString) return line.slice(0, i);
  }
  return line;
}

/**
 * Read `crons` out of the `[triggers]` block of a wrangler.toml.
 *
 * A deliberately small reader rather than a TOML dependency: the shape it has to
 * understand is one array of double-quoted strings with trailing `# job-id`
 * comments, and a dependency added for that would be a larger supply-chain
 * surface than the thing it parses.
 */
export function parseWranglerCrons(toml: string): string[] {
  const crons: string[] = [];
  let inTriggers = false;
  let inCronsArray = false;
  for (const raw of toml.split("\n")) {
    const line = stripComment(raw).trim();
    if (line === "") continue;
    if (!inTriggers) {
      if (line === "[triggers]") inTriggers = true;
      continue;
    }
    if (!inCronsArray) {
      if (/^crons\s*=\s*\[/.test(line)) inCronsArray = true;
      else if (line.startsWith("[")) inTriggers = false;
      continue;
    }
    for (const match of line.matchAll(/"([^"]*)"/g)) crons.push(match[1]);
    if (line.includes("]")) inCronsArray = false;
  }
  return crons;
}