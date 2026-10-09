/**
 * The alarm path for the Supabase egress restriction detector (DIG-1814).
 *
 * This is the same convention as `trigger-alarm.ts`, and it is deliberately a
 * separate file rather than a third member of that module's `AlarmClass` union.
 * `trigger-contract.ts` defines a closed union of two classes and `ALARM_CLASSES`
 * is a `Record<AlarmClass, ...>` over it; widening that union to describe a
 * condition that has nothing to do with trigger drift would push an unrelated
 * concept through the trigger contract's verdict machinery.
 *
 * The conventions it copies, unchanged:
 *
 *   the label is the class; the issue is the occurrence
 *
 * One issue per occurrence, never a comment on an open issue. A restriction
 * persists until the billing cycle turns over, and this probe runs hourly, so
 * filing per tick would open ~24 issues a day for a single incident — the
 * twelve-x #117 comment flood by another mechanism. `findOpenOccurrence` looks
 * for an open issue with this label and this exact title first and returns it
 * instead. Close the issue when the restriction lifts and the next occurrence
 * opens a fresh one.
 *
 * An unreadable issue search never suppresses an alarm: a duplicate is better
 * than a silent miss, and the search failure is logged.
 *
 * Raising never throws. An alarm that replaces a log line must not also become a
 * new way for a production tick to fail, so every outcome is reported through the
 * return value and one structured log line.
 */
import type { Env } from "./env";
import type { EgressVerdict } from "./supabase-egress";

const GH_API = "https://api.github.com";
const GH_API_VERSION = "2022-11-28";

/** Where this alarm lands, matching the other digithings-cron alarms. */
export const EGRESS_ALERT_REPO = "digithings-ai/twelve-x";

/**
 * The one class this path can raise. Red, because a 402 on production is
 * customer-facing: the Stripe webhook, invite codes, calendar and auth all sit
 * behind it.
 */
export const EGRESS_ALARM = {
  label: "supabase-egress-restricted",
  color: "d73a4a",
  description: "Supabase returned 402 on the production REST endpoint (Fair Use Policy restriction)",
  title: "Supabase production project restricted by egress quota",
} as const;

export type EgressAlarmResult = {
  label: string;
  raised: boolean;
  issue?: string;
  duplicate?: boolean;
  error?: string;
};

function ghHeaders(env: Env, json: boolean): Record<string, string> {
  return {
    Authorization: `Bearer ${env.GH_DISPATCH_TOKEN ?? ""}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": GH_API_VERSION,
    "User-Agent": "digithings-cron",
    ...(json ? { "Content-Type": "application/json" } : {}),
  };
}

function egressTitle(projectRef: string): string {
  return `${EGRESS_ALARM.title} — ${projectRef}`;
}

function egressBody(verdict: EgressVerdict, projectRef: string): string {
  return [
    `- Class: \`${EGRESS_ALARM.label}\``,
    `- Label: \`${EGRESS_ALARM.label}\``,
    `- Project: \`${projectRef}\``,
    `- Observed status: \`${verdict.status}\``,
    `- Verdict: \`${verdict.label}\``,
    "",
    verdict.message,
    "",
    "## What to do",
    "",
    "1. Read the Supabase dashboard usage page for the org. The org-level egress figure and the per-project split are only visible there; no API returns egress bytes.",
    "2. Decide what to stop serving. On the free plan an overage is a restriction, not a bill: the Fair Use Policy can pause projects, make the database read-only, or return 402 for all API requests.",
    "3. If the org needs more than the free allowance, upgrade the plan. That is the only lever that stops a repeat overage, and the first-time grace period does not come back.",
    "",
    "Raised by `apps/digithings-cron` (DIG-1814). The probe is `supabase-egress-guard` in `src/supabase-egress.ts`.",
  ].join("\n");
}

async function ensureLabel(
  env: Env,
  fetcher: typeof fetch,
): Promise<void> {
  const res = await fetcher(
    `${GH_API}/repos/${EGRESS_ALERT_REPO}/labels/${encodeURIComponent(EGRESS_ALARM.label)}`,
    { method: "GET", headers: ghHeaders(env, false) },
  );
  if (res.status !== 404) return;
  await fetcher(`${GH_API}/repos/${EGRESS_ALERT_REPO}/labels`, {
    method: "POST",
    headers: ghHeaders(env, true),
    body: JSON.stringify({
      name: EGRESS_ALARM.label,
      color: EGRESS_ALARM.color,
      description: EGRESS_ALARM.description,
    }),
  });
}

/** Open issue with this label and this exact title, or null. Never throws. */
async function findOpenOccurrence(
  env: Env,
  title: string,
  fetcher: typeof fetch,
): Promise<string | null> {
  try {
    const res = await fetcher(
      `${GH_API}/repos/${EGRESS_ALERT_REPO}/issues?state=open&labels=${encodeURIComponent(EGRESS_ALARM.label)}&per_page=100`,
      { method: "GET", headers: ghHeaders(env, false) },
    );
    if (res.status !== 200) {
      console.error(
        JSON.stringify({
          event: "supabase_egress_open_search_failed",
          status: res.status,
        }),
      );
      return null;
    }
    const rows: unknown = await res.json();
    if (!Array.isArray(rows)) {
      console.error(
        JSON.stringify({ event: "supabase_egress_open_search_not_a_list" }),
      );
      return null;
    }
    for (const row of rows as { title?: string; html_url?: string }[]) {
      if (row.title === title && typeof row.html_url === "string") {
        return row.html_url;
      }
    }
    return null;
  } catch (err) {
    console.error(
      JSON.stringify({
        event: "supabase_egress_open_search_threw",
        message: err instanceof Error ? err.message : String(err),
      }),
    );
    return null;
  }
}

/**
 * Raise the restriction alarm. Never throws; every outcome comes back in the
 * result.
 *
 * Only call this for a verdict that is actually `restricted`. An UNKNOWN result
 * is a broken or unconfigured probe, not an outage, and opening a
 * customer-facing issue for it would cry wolf on every tick until somebody binds
 * the secret.
 */
export async function raiseEgressAlarm(
  env: Env,
  verdict: EgressVerdict,
  opts: { projectRef: string; fetcher?: typeof fetch },
): Promise<EgressAlarmResult> {
  const result: EgressAlarmResult = { label: EGRESS_ALARM.label, raised: false };
  const fetcher = opts.fetcher ?? fetch;
  const title = egressTitle(opts.projectRef);

  try {
    if (!env.GH_DISPATCH_TOKEN) {
      result.error = "GH_DISPATCH_TOKEN is required to raise the egress alarm";
      return result;
    }

    await ensureLabel(env, fetcher);

    const open = await findOpenOccurrence(env, title, fetcher);
    if (open) {
      result.duplicate = true;
      result.issue = open;
      return result;
    }

    const res = await fetcher(`${GH_API}/repos/${EGRESS_ALERT_REPO}/issues`, {
      method: "POST",
      headers: ghHeaders(env, true),
      body: JSON.stringify({
        title,
        body: egressBody(verdict, opts.projectRef),
        labels: [EGRESS_ALARM.label],
      }),
    });

    if (res.status !== 201) {
      const text = await res.text();
      result.error = `GitHub issue create failed: HTTP ${res.status} ${text.slice(0, 300)}`;
      return result;
    }

    const payload = (await res.json()) as { html_url?: string };
    result.raised = true;
    result.issue = payload.html_url;
    return result;
  } catch (err) {
    result.error = err instanceof Error ? err.message : String(err);
    return result;
  }
}
