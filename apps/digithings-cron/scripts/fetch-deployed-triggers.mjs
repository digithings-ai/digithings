#!/usr/bin/env node
/**
 * Print the DEPLOYED cron trigger list of a Cloudflare Worker as a JSON array.
 *
 * This script asserts nothing on purpose. The trigger contract lives in
 * `src/triggers.ts` and there must be exactly one implementation of it, or the
 * copy in a shell script and the copy under test drift apart and the copy that
 * nobody tests is the one that runs in CI. This script only *observes*; the
 * contract check that consumes its output is the same vitest test that runs
 * locally, so a red contract fails the deployment and a green one proves the
 * deployed Worker carries every required trigger.
 *
 * Endpoint: GET /accounts/{account_id}/workers/scripts/{script_name}/schedules
 * ("Get Worker Script Schedules"), auth `Authorization: Bearer <api token>`,
 * permitted with Workers Scripts Read. The list lives at
 * `result.schedules[].cron`, not at the top level.
 *
 * Usage:
 *   CLOUDFLARE_API_TOKEN=... node scripts/fetch-deployed-triggers.mjs
 *   CLOUDFLARE_ACCOUNT_ID=... CLOUDFLARE_WORKER_NAME=digithings-cron node ...
 *
 * Exits non-zero, and prints nothing on stdout, when the call fails. A gate that
 * reads an empty list as "no crons deployed" would report five false alarms; a
 * gate that reads it as "unknown" must fail instead.
 *
 * Limits: one HTTPS request, no writes, no secrets in output.
 */
const API = "https://api.cloudflare.com/client/v4";

const accountId = process.env.CLOUDFLARE_ACCOUNT_ID;
const workerName = process.env.CLOUDFLARE_WORKER_NAME || "digithings-cron";
const token = process.env.CLOUDFLARE_API_TOKEN;

if (!accountId || !token) {
  console.error("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required");
  process.exit(2);
}

const url = `${API}/accounts/${accountId}/workers/scripts/${workerName}/schedules`;

let payload;
try {
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
    },
  });
  if (!res.ok) {
    // Deliberately does not print the token or the raw response headers.
    console.error(`schedules API returned HTTP ${res.status}`);
    process.exit(2);
  }
  payload = await res.json();
} catch (err) {
  console.error(`schedules API call failed: ${err instanceof Error ? err.message : err}`);
  process.exit(2);
}

if (!payload || payload.success !== true || !Array.isArray(payload.result?.schedules)) {
  // A changed or unexpected response shape must fail the gate, never pass it.
  console.error("schedules API response did not contain result.schedules");
  process.exit(2);
}

const crons = payload.result.schedules
  .map((entry) => entry?.cron)
  .filter((cron) => typeof cron === "string");

process.stdout.write(JSON.stringify(crons));