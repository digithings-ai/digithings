/// <reference types="node" />
/**
 * The deployed trigger list, checked against the required-trigger contract
 * (DIG-732).
 *
 * The hermetic cases below always run: they cover the schedule API call, its
 * response shape, and the retry that stops a schedule-propagation delay from
 * reading as a missing backstop.
 *
 * The live case reads the deployed Worker. It needs CLOUDFLARE_API_TOKEN
 * (Workers Scripts Read) and reads its account and script name out of
 * wrangler.toml so neither is copied into a test. Without the token it says
 * loudly that it did not verify anything and passes — a local `npm test` has no
 * account to ask. CI sets REQUIRE_DEPLOYED_CONTRACT=1, which turns that same
 * silence into a failure, because in CI an unverified contract is not green.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { checkDeployedContract, deployedSchedulesUrl, fetchDeployedTriggers } from "./deployed-triggers";
import type { Env } from "./env";
import { raiseVerdictAlarms } from "./trigger-alarm";
import { REQUIRED_TRIGGERS } from "./required-triggers";
import { describeVerdict } from "./trigger-contract";
import { accountIdFromWranglerToml, workerNameFromWranglerToml } from "./wrangler-config";

// Read from the working directory, like trigger-contract.test.ts: both run
// under `npm run ... --workspace digithings-cron`, and `import.meta.url` is a
// workers-types URL that will not typecheck against node's fileURLToPath.
const WRANGLER_TOML = readFileSync(resolve(process.cwd(), "wrangler.toml"), "utf8");

const CRON_TOKEN = process.env.CLOUDFLARE_API_TOKEN ?? "";
const REQUIRED = process.env.REQUIRE_DEPLOYED_CONTRACT === "1";
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID ?? accountIdFromWranglerToml(WRANGLER_TOML);
const SCRIPT_NAME = workerNameFromWranglerToml(WRANGLER_TOML);

// A one-row contract, taken from the real one. The retry cases below are about
// how many times the schedule API is read, not about which crons are required,
// and binding them to the whole contract would make them fail whenever a
// required trigger is genuinely absent from the repo — the case those reads are
// supposed to survive.
const RETRY_REQUIRED = REQUIRED_TRIGGERS.filter((trigger) => trigger.job === "twelve-x-asia");

function scheduleApi(crons: string[]): string {
  return deployedSchedulesUrl(ACCOUNT_ID, SCRIPT_NAME);
}

/** A fetcher that answers the schedule API with `crons` on each of `reads`. */
function scheduleFetcher(reads: string[][]): { fetcher: typeof fetch; calls: string[] } {
  const calls: string[] = [];
  let index = 0;
  const fetcher = vi.fn(async (url: string) => {
    calls.push(String(url));
    const crons = reads[Math.min(index, reads.length - 1)];
    index += 1;
    return Response.json({
      success: true,
      result: { schedules: crons.map((cron) => ({ cron, created_on: "x", modified_on: "x" })) },
    });
  }) as unknown as typeof fetch;
  return { fetcher, calls };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("reading the deployed trigger list", () => {
  it("addresses the schedules API for this account and script", async () => {
    const { fetcher, calls } = scheduleFetcher([["52 * * * MON-FRI"]]);
    await fetchDeployedTriggers({ accountId: ACCOUNT_ID, scriptName: SCRIPT_NAME, token: "t", fetcher });
    expect(calls[0]).toBe(
      `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/digithings-cron/schedules`,
    );
    expect(scheduleApi([])).toBe(calls[0]);
  });

  it("reads cron out of result.schedules[]", async () => {
    const { fetcher } = scheduleFetcher([["7 0 * * MON-FRI", "52 * * * MON-FRI"]]);
    const crons = await fetchDeployedTriggers({
      accountId: ACCOUNT_ID,
      scriptName: SCRIPT_NAME,
      token: "t",
      fetcher,
    });
    expect(crons).toEqual(["7 0 * * MON-FRI", "52 * * * MON-FRI"]);
  });

  it("tolerates an array of bare cron strings", async () => {
    const fetcher = (async () => Response.json({ success: true, result: { schedules: ["52 * * * MON-FRI"] } })) as unknown as typeof fetch;
    expect(
      await fetchDeployedTriggers({ accountId: ACCOUNT_ID, scriptName: SCRIPT_NAME, token: "t", fetcher }),
    ).toEqual(["52 * * * MON-FRI"]);
  });

  it("fails loudly on a non-2xx, so a broken read is never a green contract", async () => {
    const fetcher = (async () => new Response("nope", { status: 403 })) as unknown as typeof fetch;
    await expect(
      fetchDeployedTriggers({ accountId: ACCOUNT_ID, scriptName: SCRIPT_NAME, token: "t", fetcher }),
    ).rejects.toThrow(/HTTP 403/);
  });

  it("fails loudly when the API reports success:false", async () => {
    const fetcher = (async () =>
      Response.json({ success: false, errors: [{ code: 10000, message: "no script" }] })) as unknown as typeof fetch;
    await expect(
      fetchDeployedTriggers({ accountId: ACCOUNT_ID, scriptName: SCRIPT_NAME, token: "t", fetcher }),
    ).rejects.toThrow(/10000 no script/);
  });

  it("re-reads before it calls a just-deployed contract unmet", async () => {
    const asiaCron = RETRY_REQUIRED[0].cron;
    const { fetcher, calls } = scheduleFetcher([[], [asiaCron]]);
    const outcome = await checkDeployedContract({
      accountId: ACCOUNT_ID,
      scriptName: SCRIPT_NAME,
      token: "t",
      fetcher,
      attempts: 3,
      delayMs: 0,
      required: RETRY_REQUIRED,
    });
    expect(outcome.verdict.ok).toBe(true);
    expect(outcome.attempts).toBe(2);
    expect(calls).toHaveLength(2);
  });

  it("reports the failure after the last read, not the first", async () => {
    const { fetcher, calls } = scheduleFetcher([[]]);
    const outcome = await checkDeployedContract({
      accountId: ACCOUNT_ID,
      scriptName: SCRIPT_NAME,
      token: "t",
      fetcher,
      attempts: 3,
      delayMs: 0,
      required: RETRY_REQUIRED,
    });
    expect(outcome.verdict.ok).toBe(false);
    expect(outcome.attempts).toBe(3);
    expect(calls).toHaveLength(3);
    expect(outcome.verdict.missing.map((row) => row.cron)).toContain(RETRY_REQUIRED[0].cron);
  });
});

describe("the deployed Worker, checked against the required-trigger contract", () => {
  it(
    "every required cron is present in the deployed trigger list",
    // Vitest 4 takes options as the second argument; three retries of a
    // propagating deploy read are slower than the default 5s timeout.
    { timeout: 120_000 },
    async () => {
      if (CRON_TOKEN === "") {
        const message =
          "[deployed contract] NOT VERIFIED — CLOUDFLARE_API_TOKEN is not set, so the deployed trigger list was never read. A green run here proves nothing about the deployment.";
        if (REQUIRED) throw new Error(message);
        // stderr, not console.warn: vitest's default reporter swallows console
        // output from passing tests, and a run that verified nothing must not
        // be able to look like a run that verified everything.
        process.stderr.write(`${message}\n`);
        return;
      }
      const outcome = await checkDeployedContract({
        accountId: ACCOUNT_ID,
        scriptName: SCRIPT_NAME,
        token: CRON_TOKEN,
      });
      const source = `the deployed trigger list of Worker ${SCRIPT_NAME} (${outcome.attempts} read(s))`;
      if (!outcome.verdict.ok) {
        // The alarm belongs on the twelve-x path, and it fires once the
        // retries are exhausted, so a propagation delay never raises an issue.
        const results = await raiseVerdictAlarms(
          { GH_DISPATCH_TOKEN: process.env.GH_DISPATCH_TOKEN },
          outcome.verdict,
          source,
        );
        for (const result of results) {
          console.error(JSON.stringify({ ...result, source, raised: result.raised }));
        }
      }
      expect(describeVerdict(outcome.verdict, source)).toEqual([
        `trigger contract satisfied against ${source} (${outcome.crons.length} crons)`,
      ]);
    },
  );
});