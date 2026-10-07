/// <reference types="node" />
/**
 * The required-trigger contract (DIG-732), as the assertion of record.
 *
 * These are the regression tests for DIG-553 Finding 1. Each one deletes or adds
 * a line in `wrangler.toml` and moves the matching job row, exactly as the
 * original drift did, and asserts two things at once: the contract check fails,
 * and the alarm that fires is the right class. A PR-body claim that "this would
 * have been caught" is not the control; these are.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { JOBS, type Job } from "./jobs";
import { REQUIRED_TRIGGERS, type RequiredTrigger, requiredCrons } from "./required-triggers";
import { alarmsFor, ALARM_CLASSES, ALERT_REPO, alarmBody, alarmTitle } from "./trigger-alarm";
import {
  checkTriggerContract,
  describeVerdict,
  MISSING_REQUIRED_CRON,
  unrecognisedCronViolation,
  UNRECOGNISED_CRON,
} from "./trigger-contract";
import {
  accountIdFromWranglerToml,
  cronsFromWranglerToml,
  withCronLine,
  workerNameFromWranglerToml,
  withoutLine,
} from "./wrangler-config";

// The real deploy config, read at test time so this file is the assertion of
// record for what the repo would ship — not a copy of it, which is the thing
// that let Finding 1 through. Resolved from the working directory because both
// entry points run it there (`npm run test --workspace digithings-cron`, and
// `npm run check:deployed-triggers` from the deploy workflow). A run from the
// wrong directory fails loudly with ENOENT rather than passing on a fixture.
// `import.meta.url` is deliberately unused: @cloudflare/workers-types declares
// its own URL, which does not typecheck against node's fileURLToPath.
const WRANGLER_TOML = readFileSync(resolve(process.cwd(), "wrangler.toml"), "utf8");

/** The job map `from`, with the rows named by `ids` removed. */
function withoutJobs(ids: readonly string[], from: readonly Job[] = JOBS): Job[] {
  return from.filter((job) => !ids.includes(job.id));
}

/**
 * A minimal deploy config whose `[triggers]` holds exactly `triggers`.
 *
 * Built from the contract rather than copied out of wrangler.toml on purpose.
 * The scenarios below delete one line and assert what the check then says; if
 * they deleted from the real file instead, then deleting a required trigger for
 * real would break the fixture guarding it — the suite would error out at
 * collection and the assertion that would have caught the drift would never
 * run. (Found the hard way: this file errored with "no line contains
 * twelve-x-session-catchup" in exactly the situation it exists to catch.)
 * Against the real file, the contract is checked in its own describe block.
 */
/**
 * Job rows for `triggers` and nothing else, for the same reason: a scenario
 * must be able to delete one row and still see exactly one missing trigger.
 */
function jobsForContract(triggers: readonly RequiredTrigger[] = REQUIRED_TRIGGERS): Job[] {
  return triggers.map((trigger) => ({
    id: trigger.job,
    cron: trigger.cron,
    repo: "digithings-ai/twelve-x",
    kind: "workflow_dispatch",
    enabled: true,
  }));
}

function configFor(triggers: readonly RequiredTrigger[] = REQUIRED_TRIGGERS): string {
  const rows = triggers.map(
    (trigger, index) =>
      `  "${trigger.cron}"${index === triggers.length - 1 ? "" : ","}  # ${trigger.job}`,
  );
  return [
    'name = "digithings-cron"',
    'account_id = "ae2ea3eb4ce5f7cc9bec1478f6e60e15"',
    'main = "src/index.ts"',
    "",
    "[triggers]",
    "crons = [",
    ...rows,
    "]",
    "",
  ].join("\n");
}

describe("required-trigger contract data", () => {
  it("names the three session clocks, the catch-up and the heartbeat", () => {
    expect(requiredCrons()).toEqual([
      "7 0 * * MON-FRI",
      "12 7 * * MON-FRI",
      "17 12 * * MON-FRI",
      "52 * * * MON-FRI",
      "3 6,18 * * *",
    ]);
    expect(REQUIRED_TRIGGERS.map((trigger) => trigger.job)).toEqual([
      "twelve-x-asia",
      "twelve-x-london",
      "twelve-x-new-york",
      "twelve-x-session-catchup",
      "twelve-x-primemarket-heartbeat",
    ]);
  });

  it("gives every trigger a reason, a loss and the finding that makes it a control", () => {
    for (const trigger of REQUIRED_TRIGGERS) {
      expect(trigger.reason.length, trigger.job).toBeGreaterThan(20);
      expect(trigger.lost.length, trigger.job).toBeGreaterThan(20);
      expect(trigger.evidence, trigger.job).toContain("DIG-553");
    }
  });

  it("points at job rows that exist, are enabled, and still own the cron", () => {
    for (const trigger of REQUIRED_TRIGGERS) {
      const job = JOBS.find((row) => row.id === trigger.job);
      expect(job, trigger.job).toBeDefined();
      expect(job?.enabled, trigger.job).toBe(true);
      expect(job?.cron, trigger.job).toBe(trigger.cron);
      expect(job?.repo, trigger.job).toBe("digithings-ai/twelve-x");
    }
  });
});

describe("the repo's own deploy config satisfies the contract", () => {
  it("[triggers].crons in wrangler.toml equals uniqueEnabledCrons() in order", () => {
    const enabled: string[] = [];
    const seen = new Set<string>();
    for (const job of JOBS) {
      if (!job.enabled || seen.has(job.cron)) continue;
      seen.add(job.cron);
      enabled.push(job.cron);
    }
    expect(cronsFromWranglerToml(WRANGLER_TOML)).toEqual(enabled);
  });

  it("no violation is raised against wrangler.toml", () => {
    const crons = cronsFromWranglerToml(WRANGLER_TOML);
    const verdict = checkTriggerContract(crons);
    // The count is read from the config, never written here. A literal would be a
    // second source of truth that goes red every time any cron is added on
    // develop — the same brittleness DIG-732 removed from jobs.test.ts, and the
    // same class of copy that let the deleted backstop pass unnoticed.
    expect(describeVerdict(verdict, "wrangler.toml")).toEqual([
      `trigger contract satisfied against wrangler.toml (${crons.length} crons)`,
    ]);
    expect(verdict.ok).toBe(true);
  });

  it("reads the Worker identity the schedule API is addressed by", () => {
    expect(workerNameFromWranglerToml(WRANGLER_TOML)).toBe("digithings-cron");
    expect(accountIdFromWranglerToml(WRANGLER_TOML)).toMatch(/^[0-9a-f]{32}$/);
  });
});

describe("regression: the backstop deleted from the job map and from the config together", () => {
  // The exact shape of DIG-553 Finding 1. Both halves removed, so nothing in the
  // repo is inconsistent — and, before DIG-732, nothing was red.
  const config = withoutLine(configFor(), "twelve-x-session-catchup");
  const jobs = withoutJobs(["twelve-x-session-catchup"], jobsForContract());
  const verdict = checkTriggerContract(cronsFromWranglerToml(config), { jobs });

  it("fails the contract", () => {
    expect(verdict.ok).toBe(false);
    expect(verdict.missing).toHaveLength(1);
    expect(verdict.missing[0].class).toBe(MISSING_REQUIRED_CRON);
    expect(verdict.missing[0].cron).toBe("52 * * * MON-FRI");
    expect(verdict.missing[0].job).toBe("twelve-x-session-catchup");
  });

  it("reports the absence, not an unrecognised cron", () => {
    expect(verdict.unrecognised).toEqual([]);
    expect(verdict.violations).toHaveLength(1);
  });

  it("raises the missing-cron alarm and names what is lost", () => {
    const alarms = alarmsFor(verdict.violations, "the deployed trigger list");
    expect(alarms).toHaveLength(1);
    const [alarm] = alarms;
    expect(alarm.class).toBe(MISSING_REQUIRED_CRON);
    expect(alarm.subject).toBe("52 * * * MON-FRI (twelve-x-session-catchup)");
    expect(ALARM_CLASSES[alarm.class].label).toBe("cron-missing-required-trigger");
    expect(alarmTitle(alarm)).toBe(
      "Required cron trigger absent — 52 * * * MON-FRI (twelve-x-session-catchup)",
    );
    const body = alarmBody(alarm);
    expect(body).toContain("the deployed trigger list");
    expect(body).toContain("zero catch-up runs");
    expect(body).toContain("cron-missing-required-trigger");
  });
});

describe("regression: one of the three session clocks deleted", () => {
  const config = withoutLine(configFor(), "twelve-x-new-york");
  const jobs = withoutJobs(["twelve-x-new-york"], jobsForContract());
  const verdict = checkTriggerContract(cronsFromWranglerToml(config), { jobs });

  it("fails the contract with the missing-cron class", () => {
    expect(verdict.ok).toBe(false);
    expect(verdict.missing).toHaveLength(1);
    expect(verdict.missing[0].class).toBe(MISSING_REQUIRED_CRON);
    expect(verdict.missing[0].cron).toBe("17 12 * * MON-FRI");
    expect(verdict.unrecognised).toEqual([]);
  });

  it("raises the same alarm as the backstop deletion", () => {
    const alarms = alarmsFor(verdict.violations, "the deployed trigger list");
    expect(alarms.map((alarm) => alarm.class)).toEqual([MISSING_REQUIRED_CRON]);
    expect(alarms[0].subject).toBe("17 12 * * MON-FRI (twelve-x-new-york)");
    expect(alarmBody(alarms[0])).toContain("No new-york research for the day");
  });
});

describe("regression: a session clock whose job row still exists but is disabled", () => {
  const verdict = checkTriggerContract(cronsFromWranglerToml(configFor()), {
    jobs: jobsForContract().map((job) =>
      job.id === "twelve-x-london" ? { ...job, enabled: false } : job,
    ),
  });

  it("is a missing required cron, and its cron is not also called unrecognised", () => {
    expect(verdict.ok).toBe(false);
    expect(verdict.missing).toHaveLength(1);
    expect(verdict.missing[0].reason).toContain("is disabled");
    expect(verdict.unrecognised).toEqual([]);
  });
});

describe("regression: an unknown cron added to wrangler.toml", () => {
  const config = withCronLine(configFor(), "13 4 * * *");
  const verdict = checkTriggerContract(cronsFromWranglerToml(config), {
    jobs: jobsForContract(),
  });

  it("reads as the unrecognised-cron class, never the missing-cron class", () => {
    expect(verdict.ok).toBe(false);
    expect(verdict.missing).toEqual([]);
    expect(verdict.unrecognised).toHaveLength(1);
    expect(verdict.unrecognised[0].class).toBe(UNRECOGNISED_CRON);
    expect(verdict.unrecognised[0].cron).toBe("13 4 * * *");
    expect(verdict.unrecognised[0].job).toBeNull();
  });

  it("raises a different label, colour and title from a missing required cron", () => {
    const [alarm] = alarmsFor(verdict.violations, "the deployed trigger list");
    expect(alarm.class).toBe(UNRECOGNISED_CRON);
    expect(alarm.subject).toBe("13 4 * * *");
    expect(alarmTitle(alarm)).toBe("Unrecognised cron trigger — 13 4 * * *");
    expect(ALARM_CLASSES[alarm.class].label).toBe("cron-unrecognised-trigger");
    expect(ALARM_CLASSES[alarm.class].label).not.toBe(
      ALARM_CLASSES[MISSING_REQUIRED_CRON].label,
    );
    expect(ALARM_CLASSES[alarm.class].color).not.toBe(
      ALARM_CLASSES[MISSING_REQUIRED_CRON].color,
    );
  });

  it("raises on the twelve-x path the other FX alarms use", () => {
    expect(ALERT_REPO).toBe("digithings-ai/twelve-x");
  });
});

describe("both classes at once stay two alarms, not one", () => {
  const config = withoutLine(configFor(), "twelve-x-asia");
  const jobs = withoutJobs(["twelve-x-asia"], jobsForContract());
  const withUnknown = withCronLine(config, "13 4 * * *");
  const verdict = checkTriggerContract(cronsFromWranglerToml(withUnknown), { jobs });

  it("reports the missing session clock and the stray trigger separately", () => {
    expect(verdict.violations.map((violation) => violation.class)).toEqual([
      MISSING_REQUIRED_CRON,
      UNRECOGNISED_CRON,
    ]);
    const alarms = alarmsFor(verdict.violations, "the deployed trigger list");
    expect(alarms.map((alarm) => alarm.class)).toEqual([
      MISSING_REQUIRED_CRON,
      UNRECOGNISED_CRON,
    ]);
    expect(alarms[0].subject).toBe("7 0 * * MON-FRI (twelve-x-asia)");
    expect(alarms[1].subject).toBe("13 4 * * *");
  });
});

describe("the tick path and the contract path name the same class", () => {
  it("an unmapped tick is unrecognised_cron, and never missing_required_cron", () => {
    const violation = unrecognisedCronViolation("13 4 * * *");
    expect(violation.class).toBe(UNRECOGNISED_CRON);
    expect(violation.class).not.toBe(MISSING_REQUIRED_CRON);
    const alarms = alarmsFor([violation], "the deployed trigger list, at the tick that fired");
    expect(alarms[0].subject).toBe("13 4 * * *");
    expect(alarmBody(alarms[0])).toContain("at the tick that fired");
  });

  it("an empty trigger list is a total failure, not an empty pass", () => {
    const verdict = checkTriggerContract([]);
    expect(verdict.ok).toBe(false);
    expect(verdict.missing).toHaveLength(REQUIRED_TRIGGERS.length);
  });
});