/**
 * Supabase egress quota guard (DIG-1814).
 *
 * ## What this measures, and why it is not a byte counter
 *
 * The brief for DIG-1814 asks for an alert at "80% of quota". Supabase exposes
 * **no egress-bytes figure over any API**. The whole management OpenAPI spec was
 * read for this issue; the only usage-shaped endpoints are
 * `/v1/projects/{ref}/billing/addons`,
 * `/v1/projects/{ref}/analytics/endpoints/usage.api-counts` and
 * `/v1/projects/{ref}/analytics/endpoints/usage.api-requests-count`, and those
 * count API *requests*, not bytes. There is no per-project egress endpoint, no
 * usage-bytes endpoint and no organisation-level usage endpoint. Supabase also
 * ships no configurable budget alert: the Spend Cap deliberately "doesn't allow
 * for fine-grained cost control, such as setting budgets for specific usage item
 * or receiving notifications when certain costs are reached."
 *
 * So a literal "80% of quota" byte probe cannot be built against their API. What
 * *is* observable, and what actually breaks, is the **consequence**: on the free
 * plan an overage is not a bill, it is a Fair Use Policy restriction, and one of
 * the documented restrictions is returning **402 for all API requests**. A 402 on
 * the production REST endpoint is therefore a direct, unambiguous signal that the
 * org has been restricted — which is the event this guard exists to catch.
 *
 * This module is a **restriction detector**, not a dashboard mirror. It answers
 * "is the production project being refused right now?" The human-facing quota
 * percentage still comes from the dashboard, read monthly by a person (board
 * answer on DIG-1814); `evaluateQuota` exists so that the percentage logic is
 * pure and testable the day a bytes figure is available from any source.
 *
 * ## Why UNKNOWN is a first-class answer
 *
 * A missing binding, a 401/403, a timeout and an unexpected status are all
 * UNKNOWN, never OK. The guard must never read "all clear" on the strength of a
 * check it did not actually complete.
 */

import type { Env } from "./env";
import type { ProbeFetch } from "./probe";
import { raiseEgressAlarm } from "./egress-alarm";

/** The three things this guard can honestly conclude. */
export type EgressVerdictLabel = "OK" | "RESTRICTED" | "UNKNOWN";

export type EgressVerdict = {
  label: EgressVerdictLabel;
  /** True only when the Fair Use Policy is visibly refusing requests. */
  restricted: boolean;
  /** True only when a human should be paged. Never set for UNKNOWN. */
  alert: boolean;
  message: string;
  /** 0 means "no response at all" — a transport failure, not an HTTP status. */
  status: number;
};

const EGRESS_PROBE_TIMEOUT_MS = 20_000;

/**
 * The smallest possible authenticated read: one column, one row. The response
 * body is irrelevant; only the status code carries the signal.
 */
const EGRESS_PROBE_PATH = "/rest/v1/";

/**
 * The egress target is a binding (`SUPABASE_CORE_URL`), not a static asset, so
 * there is nothing to enumerate here. `runEgressProbe` resolves it from the env.
 * Kept as an array so `probeUrls` stays a list for every ProbeKind.
 */
export const EGRESS_PROBE_URLS: readonly string[] = [];

const OK_STATUSES = new Set([200, 204, 206]);
/** Auth/config failures. Never an outage, and never a reason to page anyone. */
const AUTH_STATUSES = new Set([401, 403]);

/**
 * Classify one probe result. Pure: no I/O, no env, fully unit-testable.
 *
 * `status` of 0 means the request never produced a response (timeout, DNS
 * failure, thrown fetch). `opts.configured === false` means the bindings were
 * never resolved, so there was no probe at all.
 */
export function classifyEgress(
  status: number,
  opts: { configured?: boolean } = {},
): EgressVerdict {
  if (opts.configured === false) {
    return {
      label: "UNKNOWN",
      restricted: false,
      alert: false,
      message:
        "Supabase egress probe is not configured: SUPABASE_CORE_URL and/or SUPABASE_ANON_KEY are not bound on this Worker. No check ran.",
      status,
    };
  }

  if (status === 402) {
    return {
      label: "RESTRICTED",
      restricted: true,
      alert: true,
      message:
        "Supabase returned HTTP 402 on the production REST endpoint. On the free plan the Fair Use Policy applies 402 to all API requests once the org is over quota, so the project is restricted now. Restrictions lift at the start of the next billing cycle; a first-time grace period does not come back.",
      status,
    };
  }

  if (OK_STATUSES.has(status)) {
    return {
      label: "OK",
      restricted: false,
      alert: false,
      message: `Supabase accepted the probe (HTTP ${status}). The org is not restricted.`,
      status,
    };
  }

  if (AUTH_STATUSES.has(status)) {
    return {
      label: "UNKNOWN",
      restricted: false,
      alert: false,
      message: `Supabase returned HTTP ${status}. That is a credential or RLS problem, not a quota restriction. Check the anon key binding; do not read this as "not restricted".`,
      status,
    };
  }

  if (status === 0) {
    return {
      label: "UNKNOWN",
      restricted: false,
      alert: false,
      message:
        "No response from Supabase (timeout or transport failure). The check did not complete, so it proves nothing either way.",
      status,
    };
  }

  return {
    label: "UNKNOWN",
    restricted: false,
    alert: false,
    message: `Supabase returned an unrecognised HTTP ${status}. Not a recognised restriction signal.`,
    status,
  };
}

/**
 * Percentage-of-quota helper.
 *
 * The free plan is documented as 5 GB uncached egress plus 5 GB cached, and the
 * October 2026 overage notice said "6 GB of 5.5 GB" — 5.5 GB is neither the sum
 * nor either half, and no primary source reconciles it. Only the dashboard usage
 * page settles it. Because of that, the quota argument is a caller-supplied
 * constant rather than a baked-in figure, and this function refuses to divide by
 * an unknown quota.
 *
 * `usedBytes === null` means "not measured". That yields `{percent: null, over:
 * false}` on purpose: an absent measurement must never trip an alert.
 */
export function evaluateQuota(
  usedBytes: number | null,
  quotaBytes: number,
  thresholdPercent = 80,
): { percent: number | null; over: boolean } {
  if (usedBytes === null || !(quotaBytes > 0)) {
    return { percent: null, over: false };
  }
  const percent = (usedBytes / quotaBytes) * 100;
  return { percent, over: percent >= thresholdPercent };
}

/** Best-effort project ref for the alarm title, e.g. `rwagjbkvxkdwqmouagad`. */
export function projectRefFromUrl(url: string): string {
  try {
    return new URL(url).hostname.split(".")[0] ?? url;
  } catch {
    return url;
  }
}

/**
 * Probe the production Supabase REST endpoint and page a human if the org is
 * restricted.
 *
 * The alarm is raised *before* the throw, so the throw (which the normal cron
 * path records in the Cloudflare logs) is the local failure signal and the
 * GitHub issue is the page. Raising never throws; the throw here is the only
 * exception this function lets escape, and only for a confirmed restriction.
 */
export async function runEgressProbe(
  env: Env,
  fetchImpl: ProbeFetch,
  now: Date,
  opts: { alarmFetcher?: typeof fetch } = {},
): Promise<{ ok: true }> {
  const url = env.SUPABASE_CORE_URL;
  const key = env.SUPABASE_ANON_KEY;

  if (!url || !key) {
    const verdict = classifyEgress(0, { configured: false });
    console.log(
      JSON.stringify({
        event: "supabase_egress_probe",
        at: now.toISOString(),
        label: verdict.label,
        status: verdict.status,
        message: verdict.message,
      }),
    );
    return { ok: true };
  }

  let status = 0;
  try {
    const res = await fetchImpl(`${url.replace(/\/$/, "")}${EGRESS_PROBE_PATH}?select=*&limit=1`, {
      method: "GET",
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        "User-Agent": "digithings-cron (supabase-egress-guard)",
      },
      signal: AbortSignal.timeout(EGRESS_PROBE_TIMEOUT_MS),
    });
    status = res.status;
  } catch {
    status = 0;
  }

  const verdict = classifyEgress(status);
  console.log(
    JSON.stringify({
      event: "supabase_egress_probe",
      at: now.toISOString(),
      label: verdict.label,
      status: verdict.status,
      project: projectRefFromUrl(url),
      message: verdict.message,
    }),
  );

  if (verdict.restricted) {
    const raised = await raiseEgressAlarm(env, verdict, {
      projectRef: projectRefFromUrl(url),
      fetcher: opts.alarmFetcher,
    });
    console.log(
      JSON.stringify({
        event: "supabase_egress_alarm",
        at: now.toISOString(),
        raised: raised.raised,
        duplicate: raised.duplicate ?? false,
        issue: raised.issue ?? null,
        error: raised.error ?? null,
      }),
    );
    throw new Error(
      `supabase egress guard: production project is restricted (HTTP ${verdict.status})`,
    );
  }

  return { ok: true };
}