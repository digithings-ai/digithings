/**
 * The deployed trigger list (DIG-732).
 *
 * `wrangler.toml` is what a deploy *intends* to install. The deployed trigger
 * list is what the Worker actually fires on, and it is the second of those that
 * Finding 1 was really about: a contract satisfied by the repo but not by the
 * deployment is Finding 1 wearing a passing test. Cloudflare has no
 * introspection for a running Worker's own schedules, so the list is read from
 * the account's schedule API:
 *
 *   GET /accounts/{account_id}/workers/scripts/{script_name}/schedules
 *   -> { success: true, result: { schedules: [{ cron, created_on, modified_on }] } }
 *
 * Accepted token permission is Workers Scripts Read. Nothing here writes, and
 * nothing here reads a secret value.
 */
import { REQUIRED_TRIGGERS, type RequiredTrigger } from "./required-triggers";
import {
  checkTriggerContract,
  MISSING_REQUIRED_CRON,
  type TriggerContractVerdict,
  type TriggerViolation,
} from "./trigger-contract";

const CF_API = "https://api.cloudflare.com/client/v4";

export function deployedSchedulesUrl(accountId: string, scriptName: string): string {
  return `${CF_API}/accounts/${accountId}/workers/scripts/${encodeURIComponent(scriptName)}/schedules`;
}

type ScheduleListResponse = {
  success?: boolean;
  errors?: { code?: number; message?: string }[];
  result?: { schedules?: unknown } | unknown;
};

/** Cron expressions the deployed Worker fires on, in the order the API lists them. */
export async function fetchDeployedTriggers(opts: {
  accountId: string;
  scriptName: string;
  token: string;
  fetcher?: typeof fetch;
}): Promise<string[]> {
  const fetcher = opts.fetcher ?? fetch;
  const res = await fetcher(deployedSchedulesUrl(opts.accountId, opts.scriptName), {
    headers: {
      Authorization: `Bearer ${opts.token}`,
      Accept: "application/json",
      "User-Agent": "digithings-cron",
    },
  });
  const text = await res.text().catch(() => "");
  if (!res.ok) {
    throw new Error(`Cloudflare schedules API failed: HTTP ${res.status} ${text.slice(0, 300)}`);
  }
  let body: ScheduleListResponse;
  try {
    body = JSON.parse(text) as ScheduleListResponse;
  } catch {
    throw new Error(`Cloudflare schedules API returned non-JSON: ${text.slice(0, 200)}`);
  }
  if (body.success !== true) {
    const errors = (body.errors ?? [])
      .map((error) => `${error.code ?? "?"} ${error.message ?? ""}`.trim())
      .join("; ");
    throw new Error(`Cloudflare schedules API reported failure: ${errors || text.slice(0, 200)}`);
  }
  return readCrons(body.result);
}

/** `result.schedules[].cron`, tolerating an array of bare cron strings. */
function readCrons(result: ScheduleListResponse["result"]): string[] {
  const schedules =
    result && typeof result === "object" && "schedules" in result
      ? ((result as { schedules?: unknown }).schedules as unknown)
      : result;
  if (!Array.isArray(schedules)) {
    throw new Error("Cloudflare schedules API response has no schedules array");
  }
  const out: string[] = [];
  for (const entry of schedules) {
    if (typeof entry === "string") {
      out.push(entry);
      continue;
    }
    if (entry && typeof entry === "object" && typeof (entry as { cron?: unknown }).cron === "string") {
      out.push((entry as { cron: string }).cron);
      continue;
    }
    throw new Error("Cloudflare schedules API returned a schedule without a cron");
  }
  return out;
}

export type DeployedContract = {
  verdict: TriggerContractVerdict;
  /** The trigger list the verdict was taken against. */
  crons: string[];
  /** How many times the schedule API was read. */
  attempts: number;
  /**
   * Reads that failed outright, cleared by the first successful read. Non-empty
   * alongside `ok: true` means the gate passed only after a retry; non-empty
   * alongside `ok: false` and an exhausted `attempts` means every read failed.
   */
  readErrors: string[];
};

/**
 * Evaluate the contract against the deployed trigger list.
 *
 * A deploy installs schedules asynchronously, so the first read after a deploy
 * can read the previous set. That is why this retries before it gives up — and
 * why the alarm belongs to the caller: a caller that alarms on attempt one
 * alarms on a propagation delay. Retry until `attempts` reads all disagree with
 * the contract, then report it once.
 *
 * A read that cannot be made at all — a 5xx, a timeout, a body that is not the
 * expected shape — is retried on the same footing as a read that disagrees. A
 * transient Cloudflare error must not fail the gate on the first attempt while a
 * genuine propagation delay is given three. The exhaustion is reported as
 * `readErrors` rather than thrown, because the caller's alarm and its gate
 * decision have to be the same event: a gate that fails with nothing raised is
 * the silent outcome this whole change exists to prevent.
 */
export async function checkDeployedContract(opts: {
  accountId: string;
  scriptName: string;
  token: string;
  fetcher?: typeof fetch;
  attempts?: number;
  delayMs?: number;
  /**
   * Narrow the contract for a test. The deployed check itself always wants the
   * real one: a test that passes a different set cannot prove the gate holds.
   */
  required?: readonly RequiredTrigger[];
}): Promise<DeployedContract> {
  const attempts = Math.max(1, opts.attempts ?? 3);
  const delayMs = Math.max(0, opts.delayMs ?? 10_000);
  let crons: string[] = [];
  let verdict: TriggerContractVerdict | undefined;
  const readErrors: string[] = [];
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    let read: string[];
    try {
      read = await fetchDeployedTriggers(opts);
    } catch (error) {
      // Keep the last good list for the caller to report, so the alarm can name
      // what the deployment was last seen to have, not just that a read failed.
      readErrors.push(error instanceof Error ? error.message : String(error));
      if (attempt === attempts) {
        return {
          verdict: verdict ?? unreadableVerdict(readErrors, opts.required ?? REQUIRED_TRIGGERS),
          crons,
          attempts: attempt,
          readErrors,
        };
      }
      if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs));
      continue;
    }
    readErrors.length = 0;
    crons = read;
    verdict = checkTriggerContract(crons, { required: opts.required });
    if (verdict.ok) return { verdict, crons, attempts: attempt, readErrors };
    if (attempt < attempts && delayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  // verdict is assigned on every completed iteration above.
  return { verdict: verdict!, crons, attempts, readErrors };
}

/**
 * A verdict for "the list could never be read", kept inside the contract's own
 * vocabulary so it travels the one path the caller already handles. It is
 * reported as `missing_required_cron` on purpose: a trigger that cannot be
 * proven present is indistinguishable, for the pipeline, from one that is
 * absent, and the required-cron class is the one that says a backstop is lost.
 */
function unreadableVerdict(
  readErrors: readonly string[],
  required: readonly RequiredTrigger[],
): TriggerContractVerdict {
  const detail = readErrors[readErrors.length - 1] ?? "no detail";
  const missed: TriggerViolation[] = required.map((trigger) => ({
    class: MISSING_REQUIRED_CRON,
    cron: trigger.cron,
    job: trigger.job,
    reason: `${trigger.reason} (the deployed trigger list could not be read on any of the attempts: ${detail})`,
    lost: trigger.lost,
    evidence: trigger.evidence,
  }));
  return {
    ok: false,
    present: 0,
    missing: missed,
    unrecognised: [],
    violations: missed,
  };
}