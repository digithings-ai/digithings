/**
 * The required-trigger contract, pinned (DIG-732, DIG-553 Finding 1).
 *
 * These tests exist because of a measured failure, not a style preference.
 * Over 543 runs, 1-30 August 2026 produced zero catch-up runs, and six of the
 * twelve client-visible stale days were therefore unrecoverable. Nothing said
 * so, because `uniqueEnabledCrons()` derives the trigger set FROM the job rows:
 * delete the `twelve-x-session-catchup` row AND its cron line and every old
 * assertion stayed green.
 *
 * The contract below is asserted from three directions so it cannot be passed
 * by deleting anything:
 *
 *   - against the real `wrangler.toml`, as it is committed;
 *   - against the DEPLOYED trigger list when CI supplies it;
 *   - against the specific deletions that produced Finding 1, asserting the
 *     alarm class each one raises.
 *
 * A deletion test that only asserted "the evaluator returns ok: false" would
 * pass even if nothing alarmed. Each one asserts the alarm body.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import wranglerToml from "../wrangler.toml?raw";
import type { Env } from "./env";
import { JOBS, uniqueEnabledCrons } from "./jobs";
import worker from "./index";
import { renderTriggerAlarm, raiseTriggerAlarms } from "./trigger-alarm";
import {
  REQUIRED_CRON_ABSENT,
  REQUIRED_TRIGGERS,
  UNMAPPED_CRON,
  contractGaps,
  evaluateTriggerContract,
  parseTriggerListJson,
  parseWranglerCrons,
  type RequiredTrigger,
} from "./triggers";

/**
 * The deployed list, when CI supplies it. The deploy workflow writes
 * `DIGITHINGS_CRON_DEPLOYED_TRIGGERS` to $GITHUB_ENV from the Cloudflare
 * schedules API before the test step runs. Unset locally, so the same suite
 * asserts the repo side. One implementation either way: this test file.
 */
declare const process: { env: Record<string, string | undefined> };

const DEPLOYED_RAW = process.env.DIGITHINGS_CRON_DEPLOYED_TRIGGERS ?? "";
const hasDeployedList = DEPLOYED_RAW.trim().length > 0;

function deployedCrons(): string[] {
  return parseTriggerListJson(DEPLOYED_RAW);
}

const REPO_CRONS = parseWranglerCrons(wranglerToml);

/** An alarm env with one fetch spy; every comment must land on the same issue. */
function alarmEnv(): { env: Env; posts: Array<{ url: string; body: string }> } {
  const posts: Array<{ url: string; body: string }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: unknown, init?: { body?: string }) => {
      posts.push({ url: String(input), body: String(init?.body ?? "") });
      return new Response("{}", { status: 201 });
    }),
  );
  return {
    env: {
      GH_DISPATCH_TOKEN: "gh-token",
      ALERT_ISSUE_REPO: "digithings-ai/digithings",
      ALERT_ISSUE_NUMBER: "4761",
    },
    posts,
  };
}

function executionContext(promises: Promise<unknown>[]): ExecutionContext {
  return {
    waitUntil(promise: Promise<unknown>) {
      promises.push(promise);
    },
  } as unknown as ExecutionContext;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the contract as data", () => {
  it("names the three FX session crons, the catch-up and the heartbeat", () => {
    const crons = REQUIRED_TRIGGERS.map((t) => t.cron);
    expect(crons).toEqual([
      "7 0 * * MON-FRI",
      "12 7 * * MON-FRI",
      "17 12 * * MON-FRI",
      "52 * * * MON-FRI",
      "3 6,18 * * *",
    ]);
  });

  it("gives every required trigger a reason a client could care about", () => {
    for (const trigger of REQUIRED_TRIGGERS) {
      expect(trigger.reason.length).toBeGreaterThan(40);
      expect(trigger.reason).toMatch(/[.]/);
    }
  });

  it("names a job that exists and is enabled for every required trigger", () => {
    expect(contractGaps()).toEqual([]);
  });

  it("spells each required cron exactly as jobs.ts and wrangler.toml spell it", () => {
    const mapped = uniqueEnabledCrons();
    for (const trigger of REQUIRED_TRIGGERS) {
      expect(mapped).toContain(trigger.cron);
      const jobs = JOBS.filter((j) => j.cron === trigger.cron && j.enabled);
      expect(jobs.map((j) => j.id)).toContain(trigger.job);
    }
  });

  it("keeps the two alarm classes distinct", () => {
    expect(REQUIRED_CRON_ABSENT).not.toBe(UNMAPPED_CRON);
    const absent = evaluateTriggerContract([]);
    expect(absent.violations.map((v) => v.alarm_class)).toEqual([
      REQUIRED_CRON_ABSENT,
      REQUIRED_CRON_ABSENT,
      REQUIRED_CRON_ABSENT,
      REQUIRED_CRON_ABSENT,
      REQUIRED_CRON_ABSENT,
    ]);
    const unmapped = evaluateTriggerContract([...REPO_CRONS, "5 5 * * *"]);
    expect(unmapped.violations.map((v) => v.alarm_class)).toEqual([UNMAPPED_CRON]);
  });
});

describe("reading wrangler.toml", () => {
  it("reads every cron the file declares", () => {
    // The reader must not quietly drop entries: a parser that returns a short
    // list would make an absent required cron look present.
    expect(REPO_CRONS.length).toBe(new Set(REPO_CRONS).size);
    expect(REPO_CRONS.length).toBeGreaterThanOrEqual(REQUIRED_TRIGGERS.length);
    expect(REPO_CRONS).toContain("52 * * * MON-FRI");
    expect(REPO_CRONS).toContain("3 6,18 * * *");
  });

  it("does not read comments as crons", () => {
    expect(REPO_CRONS.every((c) => !c.includes("#"))).toBe(true);
    expect(parseWranglerCrons('[triggers]\ncrons = ["1 2 * * *"] # note\n')).toEqual([
      "1 2 * * *",
    ]);
  });

  it("returns nothing when there is no triggers block", () => {
    expect(parseWranglerCrons('name = "x"\n[vars]\nA = "1"\n')).toEqual([]);
  });
});

describe("reading the deployed trigger list", () => {
  // This is the boundary between the Cloudflare schedules API and the contract.
  // A malformed observation must throw, not degrade into "no crons deployed",
  // because an empty list is indistinguishable from a wiped deployment and
  // would raise five false alarms instead of one true one.
  it("accepts the JSON array the fetch script emits", () => {
    expect(parseTriggerListJson('["52 * * * MON-FRI","3 6,18 * * *"]')).toEqual([
      "52 * * * MON-FRI",
      "3 6,18 * * *",
    ]);
    expect(parseTriggerListJson("[]")).toEqual([]);
  });

  it("rejects a list that is not an array of strings", () => {
    expect(() => parseTriggerListJson('{"cron":"52 * * * MON-FRI"}')).toThrow(/not a JSON array/);
    expect(() => parseTriggerListJson('["52 * * * MON-FRI",null]')).toThrow(/non-string/);
    expect(() => parseTriggerListJson("not json")).toThrow();
  });

  it("treats an empty deployed list as five absent triggers, not as green", () => {
    // Proves the failure direction: an empty observation is a red contract, so a
    // broken fetch cannot quietly pass the gate.
    const result = evaluateTriggerContract(parseTriggerListJson("[]"));
    expect(result.ok).toBe(false);
    expect(result.violations).toHaveLength(REQUIRED_TRIGGERS.length);
    expect(result.violations.every((v) => v.alarm_class === REQUIRED_CRON_ABSENT)).toBe(true);
  });
});

describe("a green contract run", () => {
  it("proves every required cron is present in the committed trigger list", () => {
    const result = evaluateTriggerContract(REPO_CRONS);
    expect(result.violations).toEqual([]);
    expect(result.ok).toBe(true);
    expect(result.checked).toBe(REQUIRED_TRIGGERS.length);
  });

  it.skipIf(!hasDeployedList)(
    "proves every required cron is present in the DEPLOYED trigger list",
    () => {
      const deployed = deployedCrons();
      const result = evaluateTriggerContract(deployed);
      if (!result.ok) {
        const detail = result.violations
          .map((v) =>
            v.alarm_class === UNMAPPED_CRON
              ? `  unmapped_cron: ${v.cron}`
              : `  required_cron_absent: ${v.job} (${v.cron}) — ${v.reason}`,
          )
          .join("\n");
        throw new Error(
          `The deployed digithings-cron trigger list does not satisfy the ` +
            `required-trigger contract:\n${detail}`,
        );
      }
      expect(result.checked).toBe(REQUIRED_TRIGGERS.length);
    },
  );
});

describe("acceptance: deleting the catch-up row and its cron together", () => {
  // The exact shape of DIG-553 Finding 1. Both sides of the pair go, so the old
  // job -> cron assertion had nothing to disagree with.
  const crons = REPO_CRONS.filter((c) => c !== "52 * * * MON-FRI");
  const mapped = uniqueEnabledCrons().filter((c) => c !== "52 * * * MON-FRI");

  it("no longer satisfies the contract", () => {
    const result = evaluateTriggerContract(crons, { mappedCrons: mapped });
    expect(result.ok).toBe(false);
    expect(result.violations).toHaveLength(1);
    const [violation] = result.violations;
    expect(violation.alarm_class).toBe(REQUIRED_CRON_ABSENT);
    if (violation.alarm_class !== REQUIRED_CRON_ABSENT) throw new Error("wrong class");
    expect(violation.job).toBe("twelve-x-session-catchup");
    expect(violation.cron).toBe("52 * * * MON-FRI");
  });

  it("raises a required_cron_absent alarm that names the job and the reason", async () => {
    const { env, posts } = alarmEnv();
    const [violation] = evaluateTriggerContract(crons, { mappedCrons: mapped }).violations;

    await raiseTriggerAlarms(env, [violation]);

    expect(posts).toHaveLength(1);
    expect(posts[0].url).toBe(
      "https://api.github.com/repos/digithings-ai/digithings/issues/4761/comments",
    );
    expect(posts[0].body).toContain("required_cron_absent");
    expect(posts[0].body).toContain("twelve-x-session-catchup");
    expect(posts[0].body).toContain("52 * * * MON-FRI");
    expect(posts[0].body).toContain("DIG-553");
    // The missing-cron alarm must not read like the unmapped-cron one.
    expect(posts[0].body).not.toContain("unmapped_cron");
  });
});

describe("acceptance: deleting one of the three session crons", () => {
  const dropped: RequiredTrigger = {
    job: "twelve-x-london",
    cron: "12 7 * * MON-FRI",
    reason: "test stand-in",
  };
  const crons = REPO_CRONS.filter((c) => c !== dropped.cron);
  const mapped = uniqueEnabledCrons().filter((c) => c !== dropped.cron);

  it("no longer satisfies the contract, with the same failure", () => {
    const result = evaluateTriggerContract(crons, { mappedCrons: mapped });
    expect(result.ok).toBe(false);
    const classes = result.violations.map((v) => v.alarm_class);
    expect(classes).toEqual([REQUIRED_CRON_ABSENT]);
    // The dropped cron is gone from the job rows too, so it must NOT also read
    // as unmapped. One fault, one class.
    expect(classes).not.toContain(UNMAPPED_CRON);
    expect(dropped.cron).toBe("12 7 * * MON-FRI");
    expect(REQUIRED_TRIGGERS.map((t) => t.cron)).toContain(dropped.cron);
  });

  it("raises a required_cron_absent alarm carrying the contract's reason", async () => {
    const { env, posts } = alarmEnv();
    const [violation] = evaluateTriggerContract(crons, { mappedCrons: mapped }).violations;

    await raiseTriggerAlarms(env, [violation]);

    expect(posts).toHaveLength(1);
    expect(posts[0].body).toContain("required_cron_absent");
    expect(posts[0].body).toContain(dropped.cron);
    expect(posts[0].body).not.toContain("unmapped_cron");
  });
});

describe("acceptance: an unknown cron added to wrangler.toml", () => {
  // The contract's crons are all still deployed, so the fault is purely the
  // extra trigger. It must read as the unrecognised-cron class.
  const crons = [...REPO_CRONS, "5 5 * * *"];

  it("alarms with the unmapped class, not the missing-cron class", () => {
    const result = evaluateTriggerContract(crons);
    expect(result.ok).toBe(false);
    expect(result.violations).toHaveLength(1);
    const [violation] = result.violations;
    expect(violation.alarm_class).toBe(UNMAPPED_CRON);
    if (violation.alarm_class !== UNMAPPED_CRON) throw new Error("wrong class");
    expect(violation.cron).toBe("5 5 * * *");
  });

  it("raises an alarm that reads differently from a missing-cron alarm", async () => {
    const { env, posts } = alarmEnv();
    const [violation] = evaluateTriggerContract(crons).violations;

    await raiseTriggerAlarms(env, [violation]);

    expect(posts).toHaveLength(1);
    expect(posts[0].body).toContain("unmapped_cron");
    expect(posts[0].body).toContain("5 5 * * *");
    // Distinct classes must read distinctly: the missing-cron class must not
    // appear in a body that is reporting the opposite fault.
    expect(posts[0].body).not.toContain("required_cron_absent");
  });

  it("states in words that required triggers are still present", () => {
    const body = renderTriggerAlarm({
      alarm_class: UNMAPPED_CRON,
      cron: "5 5 * * *",
    });
    expect(body).toContain("NOT a missing-trigger fault");
  });

  it("fires the alarm when the deployed Worker actually receives that cron", async () => {
    // The end-to-end shape: a real scheduled() tick with a cron nothing claims.
    const { env, posts } = alarmEnv();
    const pending: Promise<unknown>[] = [];

    await worker.scheduled(
      { cron: "5 5 * * *", scheduledTime: Date.UTC(2026, 9, 5, 5, 0) } as ScheduledController,
      env,
      executionContext(pending),
    );
    await Promise.all(pending);

    expect(posts).toHaveLength(1);
    expect(posts[0].url).toBe(
      "https://api.github.com/repos/digithings-ai/digithings/issues/4761/comments",
    );
    expect(posts[0].body).toContain("unmapped_cron");
  });

  it("stays quiet for a cron that only paused jobs claim", async () => {
    // The false-alarm tax guard. "17 10 * * *" belongs to the disabled
    // house-run retries: nothing dispatches, which is the correct behaviour for
    // a deliberately paused trigger. If this alarmed, every paused job would
    // page, and a control that cries wolf gets switched off — which is how the
    // FX backstop went missing in the first place.
    const { env, posts } = alarmEnv();
    const pending: Promise<unknown>[] = [];

    await worker.scheduled(
      { cron: "17 10 * * *", scheduledTime: Date.UTC(2026, 9, 5, 10, 0) } as ScheduledController,
      env,
      executionContext(pending),
    );
    await Promise.all(pending);

    expect(JOBS.filter((j) => j.cron === "17 10 * * *").every((j) => !j.enabled)).toBe(true);
    expect(posts).toHaveLength(0);
    expect(pending).toHaveLength(0);
  });
});

describe("alarm delivery", () => {
  it("does not throw when GitHub refuses, and still returns the short days", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("nope", { status: 403 })),
    );
    const violations = evaluateTriggerContract([]).violations;

    await expect(
      raiseTriggerAlarms(
        {
          GH_DISPATCH_TOKEN: "gh-token",
          ALERT_ISSUE_REPO: "digithings-ai/digithings",
          ALERT_ISSUE_NUMBER: "4761",
        },
        violations,
      ),
    ).resolves.toBe(false);
  });

  it("does not throw when the alarm env is not configured", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 201 })));
    const fetchSpy = vi.mocked(fetch);

    await expect(
      raiseTriggerAlarms({ GH_DISPATCH_TOKEN: "gh-token" }, [
        { alarm_class: UNMAPPED_CRON, cron: "5 5 * * *" },
      ]),
    ).resolves.toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("posts one comment per violation so counts stay countable", async () => {
    const { env, posts } = alarmEnv();
    const violations = evaluateTriggerContract(["5 5 * * *", "6 6 * * *"]).violations;

    await raiseTriggerAlarms(env, violations);

    expect(violations.length).toBeGreaterThan(1);
    expect(posts).toHaveLength(violations.length);
    expect(new Set(posts.map((p) => p.body)).size).toBe(violations.length);
  });

  it("posts nothing when the contract holds", async () => {
    const { env, posts } = alarmEnv();

    await raiseTriggerAlarms(env, evaluateTriggerContract(REPO_CRONS).violations);

    expect(posts).toHaveLength(0);
  });
});