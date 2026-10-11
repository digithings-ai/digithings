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
// `||`, not `??`: Actions renders an unset secret as an empty string, and
// `"" ?? fallback` is still `""`, so the fallback would never run and the request
// would go to `/accounts//workers/...`. That fails closed either way, but the
// resulting error names an empty account id instead of the real one.
const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID || accountIdFromWranglerToml(WRANGLER_TOML);
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

  // The retry is for reads that fail, not only for reads that disagree. Before
  // this, a single Cloudflare 5xx on the first read failed the gate on attempt
  // one and raised nothing, because the throw escaped the loop and the caller
  // only alarms on a verdict.
  it("retries a read that errors instead of failing on the first attempt", async () => {
    const asiaCron = RETRY_REQUIRED[0].cron;
    const calls: string[] = [];
    let index = 0;
    const answers = [
      () => new Response("upstream boom", { status: 500 }),
      () => Response.json({
        success: true,
        result: { schedules: [{ cron: asiaCron, created_on: "x", modified_on: "x" }] },
      }),
    ];
    const fetcher = vi.fn(async (url: string) => {
      calls.push(String(url));
      const answer = answers[Math.min(index, answers.length - 1)];
      index += 1;
      return answer();
    }) as unknown as typeof fetch;

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
    // The gate passed, but only after a retry, and that is on the record.
    expect(outcome.readErrors).toHaveLength(0);
  });

  it("reports an unreadable list as unmet, in the missing-required-cron class", async () => {
    const fetcher = vi.fn(async () => new Response("still 500", { status: 503 })) as unknown as typeof fetch;
    const outcome = await checkDeployedContract({
      accountId: ACCOUNT_ID,
      scriptName: SCRIPT_NAME,
      token: "t",
      fetcher,
      attempts: 2,
      delayMs: 0,
      required: RETRY_REQUIRED,
    });
    // Not green, and not a throw: the gate and the alarm have to be the same
    // event, so an unreadable list reads as a lost backstop.
    expect(outcome.verdict.ok).toBe(false);
    expect(outcome.verdict.unrecognised).toEqual([]);
    expect(outcome.verdict.missing).toHaveLength(RETRY_REQUIRED.length);
    expect(outcome.verdict.missing[0].class).toBe("missing_required_cron");
    expect(outcome.verdict.missing[0].reason).toContain("could not be read");
    expect(outcome.readErrors).toHaveLength(2);
    expect(outcome.readErrors[0]).toContain("503");
  });

  it("keeps a successful read's own verdict even if a later read errors", async () => {
    // The answer sequence here disagrees first and then fails outright. The
    // disagreeing verdict is the real finding, so it must survive the error.
    const asiaCron = RETRY_REQUIRED[0].cron;
    let index = 0;
    const answers = [
      () => Response.json({ success: true, result: { schedules: [] } }),
      () => new Response("boom", { status: 500 }),
    ];
    const fetcher = vi.fn(async () => {
      const answer = answers[Math.min(index, answers.length - 1)];
      index += 1;
      return answer();
    }) as unknown as typeof fetch;

    const outcome = await checkDeployedContract({
      accountId: ACCOUNT_ID,
      scriptName: SCRIPT_NAME,
      token: "t",
      fetcher,
      attempts: 2,
      delayMs: 0,
      required: RETRY_REQUIRED,
    });
    expect(outcome.verdict.ok).toBe(false);
    expect(outcome.verdict.missing.map((row) => row.cron)).toEqual([asiaCron]);
    expect(outcome.readErrors).toHaveLength(1);
  });
});

describe("the deployed Worker, checked against the required-trigger contract", () => {
  it(
    "every required cron is present in the deployed trigger list",
    // Options as the second argument, which vitest 4 supports alongside the
    // older `(name, fn, timeout)` form. Three retries of a propagating deploy
    // read are slower than the default 5s timeout.
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
        // `readErrors` rides along so a run that only passed after a retry, or
        // that never read the list at all, says so in the log next to the alarm.
        const results = await raiseVerdictAlarms(
          { GH_DISPATCH_TOKEN: process.env.GH_DISPATCH_TOKEN },
          outcome.verdict,
          source,
        );
        for (const result of results) {
          console.error(
            JSON.stringify({ ...result, source, raised: result.raised, readErrors: outcome.readErrors }),
          );
        }
      }
      // Assert the verdict itself, not a sentence built from `crons.length`.
      // `describeVerdict` counts distinct expressions (`verdict.present`), so a
      // duplicated cron in the API response made this read "(2 crons)" against a
      // rendered "(1 crons)" and failed a deployment that was in fact correct.
      expect(outcome.verdict.violations).toEqual([]);
      expect(outcome.verdict.ok).toBe(true);
      expect(describeVerdict(outcome.verdict, source)).toEqual([
        `trigger contract satisfied against ${source} (${outcome.verdict.present} crons)`,
      ]);
    },
  );
});