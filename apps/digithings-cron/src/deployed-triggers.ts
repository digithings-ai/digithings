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
import type { RequiredTrigger } from "./required-triggers";
import { checkTriggerContract, type TriggerContractVerdict } from "./trigger-contract";

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
};

/**
 * Evaluate the contract against the deployed trigger list.
 *
 * A deploy installs schedules asynchronously, so the first read after a deploy
 * can read the previous set. That is why this retries before it gives up — and
 * why the alarm belongs to the caller: a caller that alarms on attempt one
 * alarms on a propagation delay. Retry until `attempts` reads all disagree with
 * the contract, then report it once.
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
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    crons = await fetchDeployedTriggers(opts);
    verdict = checkTriggerContract(crons, { required: opts.required });
    if (verdict.ok) return { verdict, crons, attempts: attempt };
    if (attempt < attempts && delayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  // verdict is assigned on every completed iteration above.
  return { verdict: verdict!, crons, attempts };
}