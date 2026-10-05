/**
 * The trigger-contract alarm (DIG-732, DIG-553 Finding 1).
 *
 * Before this, a missing backstop was `console.error(JSON.stringify({cron, error:
 * "unmapped_cron"}))` — a log line nobody reads, in a file nobody diffs, for a
 * control nobody asserts. This module is the part that makes absence loud.
 *
 * It reuses the twelve-x alarm transport that DIG-71 pins: one GitHub issue
 * comment on the configured alert issue, authenticated with the same
 * `GH_DISPATCH_TOKEN` the dispatcher already holds (that coupling is risk R14 in
 * docs/ops/SECRETS_INVENTORY.md, accepted by Chris on 2026-10-05). No new
 * credential, no new binding, no extra dependency.
 *
 * The two alarm classes are rendered differently on purpose, because they are
 * different faults and an operator must not have to read carefully to tell them
 * apart:
 *
 *   required_cron_absent — cover is LOST. Nothing will fire it.
 *   unmapped_cron        — cover is being BURNED on work nobody designed.
 *
 * Failure to deliver the alarm is itself logged and swallowed. An alarm that
 * throws turns a bad deployment into a crashing Worker, and the operator then
 * has two faults instead of one. The contract's *other* half — failing the
 * deployment — is where absence is stopped, not here.
 *
 * Limits: exactly one subrequest per raise, at most one raise per cron firing.
 * The body is a few hundred bytes, well inside the 65536-byte GitHub comment
 * limit. No storage, no CPU of note.
 */
import { UNMAPPED_CRON, type TriggerContractViolation } from "./triggers";

const GH_API = "https://api.github.com";
const GH_API_VERSION = "2022-11-28";

/** The slice of Env this module needs. Keeps the test honest about the shape. */
export type AlarmEnv = {
  GH_DISPATCH_TOKEN?: string;
  ALERT_ISSUE_REPO?: string;
  ALERT_ISSUE_NUMBER?: string;
};

function renderRequiredCronAbsent(
  v: Extract<TriggerContractViolation, { alarm_class: "required_cron_absent" }>,
): string {
  return [
    "**`required_cron_absent` — a required FX trigger is NOT deployed.**",
    "",
    `- job: \`${v.job}\``,
    `- cron: \`${v.cron}\``,
    `- why it is required: ${v.reason}`,
    "",
    "This trigger is required and it is not in the deployed trigger list. Nothing " +
      "will fire it. Whatever depended on it has stopped happening, quietly, and " +
      "will stay stopped until the trigger is restored.",
    "",
    "Check `apps/digithings-cron/wrangler.toml` `[triggers].crons`, then redeploy. " +
      "The required-trigger contract in `apps/digithings-cron/src/triggers.ts` is " +
      "what failed; it is the assertion of record, not a log line.",
  ].join("\n");
}

function renderUnmappedCron(
  v: Extract<TriggerContractViolation, { alarm_class: "unmapped_cron" }>,
): string {
  return [
    "**`unmapped_cron` — a cron is DEPLOYED that no enabled job claims.**",
    "",
    `- cron: \`${v.cron}\``,
    "",
    "This trigger is live but unmapped: it fires, and the Worker finds no enabled " +
      "job to dispatch. Cost is being paid for work nobody designed. This is NOT a " +
      "missing-trigger fault — required triggers are all present as far as this " +
      "alarm can tell. Either a job row was deleted while its cron line survived, " +
      "or the cron line was added by mistake.",
    "",
    "Check `JOBS` in `apps/digithings-cron/src/jobs.ts` against " +
      "`apps/digithings-cron/wrangler.toml` `[triggers].crons`.",
  ].join("\n");
}

/**
 * Render one violation as the body of an alarm comment.
 *
 * Split out and exported so the class distinction is pinned by a test that reads
 * the body, not by a test that counts fetch calls.
 */
export function renderTriggerAlarm(violation: TriggerContractViolation): string {
  return violation.alarm_class === UNMAPPED_CRON
    ? renderUnmappedCron(violation)
    : renderRequiredCronAbsent(violation);
}

/**
 * Post one alarm comment per violation on the configured alert issue.
 *
 * Returns true when every violation was delivered. Returns false — never throws —
 * when the env is not configured or GitHub refused. The caller still logs the
 * contract failure itself, so an undelivered alarm degrades to today's behaviour
 * rather than to silence inside silence.
 */
export async function postTriggerAlarm(
  env: AlarmEnv,
  violation: TriggerContractViolation,
): Promise<boolean> {
  const repo = env.ALERT_ISSUE_REPO;
  const number = env.ALERT_ISSUE_NUMBER;
  const token = env.GH_DISPATCH_TOKEN;
  if (!repo || !number || !token) {
    console.error(
      JSON.stringify({
        error: "trigger_alarm_unconfigured",
        alarm_class: violation.alarm_class,
        cron: violation.cron,
        has_repo: Boolean(repo),
        has_number: Boolean(number),
        has_token: Boolean(token),
      }),
    );
    return false;
  }

  try {
    const res = await fetch(
      `${GH_API}/repos/${repo}/issues/${number}/comments`,
      {
        method: "POST",
        headers: {
          Authorization: `token ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": GH_API_VERSION,
          "Content-Type": "application/json",
          "User-Agent": "digithings-cron",
        },
        body: JSON.stringify({ body: renderTriggerAlarm(violation) }),
      },
    );
    if (!res.ok) {
      console.error(
        JSON.stringify({
          error: "trigger_alarm_post_failed",
          alarm_class: violation.alarm_class,
          cron: violation.cron,
          status: res.status,
        }),
      );
      return false;
    }
    return true;
  } catch (err) {
    console.error(
      JSON.stringify({
        error: "trigger_alarm_post_failed",
        alarm_class: violation.alarm_class,
        cron: violation.cron,
        detail: err instanceof Error ? err.message : String(err),
      }),
    );
    return false;
  }
}

/** Post every violation. One comment each, so counts stay countable. */
export async function raiseTriggerAlarms(
  env: AlarmEnv,
  violations: readonly TriggerContractViolation[],
): Promise<boolean> {
  const results: boolean[] = [];
  for (const violation of violations) {
    results.push(await postTriggerAlarm(env, violation));
  }
  return results.length > 0 && results.every(Boolean);
}