/**
 * The alarm path for trigger drift (DIG-732).
 *
 * Same path as the other twelve-x alarms: the GitHub Issues REST API, reached
 * with the existing GH_DISPATCH_TOKEN (Actions write, Issues read/write on
 * digithings-ai/digithings and digithings-ai/twelve-x, no Contents grant — so
 * REST only, `gh issue create` cannot use it). The convention those alarms
 * follow is documented in twelve-x `tests/test_alerting_workflows.py`:
 *
 *   the label is the class; the issue is the occurrence
 *
 * One issue per occurrence, never a comment on an open issue. The old comment
 * behaviour grew twelve-x #117 to 322 comments, which is not an alarm.
 *
 * The two classes carry different labels, different colours and different
 * titles, so a reader can tell "the backstop is gone" from "a trigger is doing
 * nothing" without opening anything:
 *
 *   missing_required_cron — red,   a cron the pipeline requires is absent
 *   unrecognised_cron     — amber, a cron fires with nothing behind it
 *
 * Raising never throws. An alarm that replaces a log line must not also become
 * a new way for a production tick to fail, so every outcome is reported through
 * the return value and one structured log line.
 */
import type { Env } from "./env";
import {
  MISSING_REQUIRED_CRON,
  UNRECOGNISED_CRON,
  type AlarmClass,
  type TriggerContractVerdict,
  type TriggerViolation,
} from "./trigger-contract";

const GH_API = "https://api.github.com";
const GH_API_VERSION = "2022-11-28";

/**
 * Where the alarms land. twelve-x owns the FX session clocks this contract
 * protects, and twelve-x is where the other FX alarms open their issues.
 */
export const ALERT_REPO = "digithings-ai/twelve-x";

/** Class -> the label that carries it, in the twelve-x alarm vocabulary. */
export const ALARM_CLASSES: Record<
  AlarmClass,
  { label: string; color: string; description: string; title: string }
> = {
  [MISSING_REQUIRED_CRON]: {
    label: "cron-missing-required-trigger",
    color: "d73a4a",
    description:
      "A cron the FX pipeline requires is absent from the digithings-cron trigger list (DIG-553 Finding 1).",
    title: "Required cron trigger absent",
  },
  [UNRECOGNISED_CRON]: {
    label: "cron-unrecognised-trigger",
    color: "fbca04",
    description:
      "A digithings-cron trigger maps to no enabled job, so it fires and starts nothing (DIG-732).",
    title: "Unrecognised cron trigger",
  },
};

/** One issue's worth of alarm: every violation of one class, plus its source. */
export type TriggerAlarm = {
  class: AlarmClass;
  /** The trigger under test, named in the issue title. */
  subject: string;
  /** Where the contract was evaluated, e.g. "the deployed trigger list". */
  source: string;
  violations: TriggerViolation[];
};

export type AlarmResult = {
  class: AlarmClass;
  label: string;
  /** True only when the issue exists. */
  raised: boolean;
  /** GitHub issue url, when raised. */
  issue?: string;
  /** Why nothing was raised. Absence is reported, never swallowed. */
  error?: string;
};

/** Group violations into one alarm per class, missing first. */
export function alarmsFor(
  violations: readonly TriggerViolation[],
  source: string,
): TriggerAlarm[] {
  const order: AlarmClass[] = [MISSING_REQUIRED_CRON, UNRECOGNISED_CRON];
  const alarms: TriggerAlarm[] = [];
  for (const alarmClass of order) {
    const rows = violations.filter((violation) => violation.class === alarmClass);
    if (rows.length === 0) continue;
    const subjects = rows.map((row) =>
      row.job === null ? row.cron : `${row.cron} (${row.job})`,
    );
    alarms.push({
      class: alarmClass,
      subject: subjects.join(", "),
      source,
      violations: rows,
    });
  }
  return alarms;
}

/** One alarm per class for a whole verdict. Empty verdict, no alarms. */
export function alarmsForVerdict(
  verdict: TriggerContractVerdict,
  source: string,
): TriggerAlarm[] {
  return alarmsFor(verdict.violations, source);
}

function bulletLines(alarm: TriggerAlarm): string[] {
  const lines: string[] = [];
  for (const violation of alarm.violations) {
    lines.push(`- \`${violation.cron}\`${violation.job === null ? "" : ` — ${violation.job}`}`);
    lines.push(`  - Class: \`${violation.class}\``);
    lines.push(`  - Required: ${violation.reason}`);
    lines.push(`  - Without it: ${violation.lost}`);
    lines.push(`  - Evidence: ${violation.evidence}`);
  }
  return lines;
}

export function alarmTitle(alarm: TriggerAlarm): string {
  return `${ALARM_CLASSES[alarm.class].title} — ${alarm.subject}`;
}

export function alarmBody(alarm: TriggerAlarm): string {
  const spec = ALARM_CLASSES[alarm.class];
  return [
    `- Class: \`${alarm.class}\``,
    `- Label: \`${spec.label}\` (the label is the class; this issue is one occurrence)`,
    `- Checked against: ${alarm.source}`,
    `- Violations: ${alarm.violations.length}`,
    "",
    ...bulletLines(alarm),
    "",
    "Raised by `apps/digithings-cron` (DIG-732). The required-trigger contract is",
    "data with reasons in `src/required-triggers.ts`; the check is in",
    "`src/trigger-contract.ts`.",
  ].join("\n");
}

/** Same headers dispatchGithub sends, so the two share one token's blast radius. */
function ghHeaders(env: Env, json: boolean): Record<string, string> {
  return {
    Authorization: `Bearer ${env.GH_DISPATCH_TOKEN ?? ""}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": GH_API_VERSION,
    "User-Agent": "digithings-cron",
    ...(json ? { "Content-Type": "application/json" } : {}),
  };
}

/** getLabel, createLabel when absent — the twelve-x alarm step, verbatim. */
async function ensureLabel(
  env: Env,
  spec: (typeof ALARM_CLASSES)[AlarmClass],
  fetcher: typeof fetch,
): Promise<void> {
  const labels = `/repos/${ALERT_REPO}/labels`;
  const existing = await fetcher(
    `${GH_API}${labels}/${encodeURIComponent(spec.label)}`,
    { headers: ghHeaders(env, false) },
  );
  if (existing.status !== 404) return;
  await fetcher(`${GH_API}${labels}`, {
    method: "POST",
    headers: ghHeaders(env, true),
    body: JSON.stringify({ name: spec.label, color: spec.color, description: spec.description }),
  });
}

/**
 * Open one issue for one occurrence. Never throws: a failed alarm is returned
 * with `raised: false` and logged, so the caller keeps its own failure as the
 * thing that fails.
 */
export async function raiseTriggerAlarm(
  env: Env,
  alarm: TriggerAlarm,
  opts: { fetcher?: typeof fetch } = {},
): Promise<AlarmResult> {
  const fetcher = opts.fetcher ?? fetch;
  const spec = ALARM_CLASSES[alarm.class];
  const result: AlarmResult = { class: alarm.class, label: spec.label, raised: false };
  try {
    if (!env.GH_DISPATCH_TOKEN) {
      result.error = "GH_DISPATCH_TOKEN is required to raise a trigger alarm";
      console.error(JSON.stringify({ ...result, cron: alarm.subject, error: result.error }));
      return result;
    }
    await ensureLabel(env, spec, fetcher);
    const res = await fetcher(`${GH_API}/repos/${ALERT_REPO}/issues`, {
      method: "POST",
      headers: ghHeaders(env, true),
      body: JSON.stringify({
        title: alarmTitle(alarm),
        body: alarmBody(alarm),
        labels: [spec.label],
      }),
    });
    if (res.status !== 201) {
      const text = await res.text().catch(() => "");
      result.error = `GitHub issue create failed: HTTP ${res.status} ${text.slice(0, 300)}`;
      console.error(
        JSON.stringify({ alarm_class: alarm.class, cron: alarm.subject, error: result.error }),
      );
      return result;
    }
    const payload = (await res.json().catch(() => ({}))) as { html_url?: string };
    result.raised = true;
    if (payload.html_url) result.issue = payload.html_url;
    console.log(
      JSON.stringify({
        alarm_class: alarm.class,
        alarm_label: spec.label,
        alarm_raised: true,
        crons: alarm.violations.map((violation) => violation.cron),
        source: alarm.source,
        issue: result.issue ?? null,
      }),
    );
    return result;
  } catch (error: unknown) {
    result.error = error instanceof Error ? error.message : String(error);
    console.error(
      JSON.stringify({ alarm_class: alarm.class, cron: alarm.subject, error: result.error }),
    );
    return result;
  }
}

/** Raise every class present in a verdict. Results come back in class order. */
export async function raiseVerdictAlarms(
  env: Env,
  verdict: TriggerContractVerdict,
  source: string,
  opts: { fetcher?: typeof fetch } = {},
): Promise<AlarmResult[]> {
  const results: AlarmResult[] = [];
  for (const alarm of alarmsForVerdict(verdict, source)) {
    results.push(await raiseTriggerAlarm(env, alarm, opts));
  }
  return results;
}

/** Raise the alarms for a bare violation list (the unmapped-cron tick path). */
export async function raiseViolationAlarms(
  env: Env,
  violations: readonly TriggerViolation[],
  source: string,
  opts: { fetcher?: typeof fetch } = {},
): Promise<AlarmResult[]> {
  const results: AlarmResult[] = [];
  for (const alarm of alarmsFor(violations, source)) {
    results.push(await raiseTriggerAlarm(env, alarm, opts));
  }
  return results;
}