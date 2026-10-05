/**
 * The alarm path for trigger drift (DIG-732).
 *
 * The contract check in `trigger-contract.test.ts` proves the two classes are
 * distinguishable. These tests prove the classes actually reach an alarm: one
 * issue per occurrence, the label is the class, on the twelve-x issues REST
 * path the other FX alarms use.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Env } from "./env";
import { REQUIRED_TRIGGERS } from "./required-triggers";
import {
  ALARM_CLASSES,
  ALERT_REPO,
  alarmsFor,
  alarmsForVerdict,
  raiseTriggerAlarm,
  raiseVerdictAlarms,
  raiseViolationAlarms,
} from "./trigger-alarm";
import {
  checkTriggerContract,
  MISSING_REQUIRED_CRON,
  unrecognisedCronViolation,
  UNRECOGNISED_CRON,
} from "./trigger-contract";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const ENV: Env = { DRY_RUN: "0", GH_DISPATCH_TOKEN: "github-token" };

type GitHubCall = { url: string; init: RequestInit };

type OpenIssue = { title: string; html_url?: string };

/**
 * A fetcher that answers the four calls the alarm makes, and records them: get
 * the label, create it when 404, search open issues for the class label, open
 * the issue. `openIssues` is what the search answers with, so a test can say
 * the drift is already on the board.
 */
function recordingFetch(
  labelStatus = 200,
  issueStatus = 201,
  openIssues: OpenIssue[] = [],
): { fetcher: typeof fetch; calls: GitHubCall[] } {
  const calls: GitHubCall[] = [];
  const fetcher = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url: String(url), init });
    if (String(url).includes("/labels/")) return new Response("{}", { status: labelStatus });
    if (String(url).endsWith("/labels")) return Response.json({ name: "label" }, { status: 201 });
    if (String(url).includes("/issues?")) return Response.json(openIssues, { status: 200 });
    if (String(url).endsWith("/issues")) {
      return Response.json(
        { html_url: `https://github.com/${ALERT_REPO}/issues/9001` },
        { status: issueStatus },
      );
    }
    return new Response("unexpected", { status: 500 });
  }) as unknown as typeof fetch;
  return { fetcher, calls };
}

function jsonBody(call: GitHubCall): Record<string, unknown> {
  return JSON.parse(String(call.init.body ?? "{}")) as Record<string, unknown>;
}

describe("raiseTriggerAlarm", () => {
  it("opens one issue in twelve-x with the class as the label", async () => {
    const { fetcher, calls } = recordingFetch();
    const violation = unrecognisedCronViolation("13 4 * * *");

    const results = await raiseViolationAlarms(
      ENV,
      [violation],
      "the deployed trigger list, at the tick that fired",
      { fetcher },
    );

    expect(results).toEqual([
      {
        class: UNRECOGNISED_CRON,
        label: "cron-unrecognised-trigger",
        raised: true,
        issue: `https://github.com/${ALERT_REPO}/issues/9001`,
      },
    ]);
    const issue = calls.at(-1);
    expect(issue?.url).toBe(`https://api.github.com/repos/${ALERT_REPO}/issues`);
    expect(issue?.init.method).toBe("POST");
    expect(jsonBody(issue!).labels).toEqual(["cron-unrecognised-trigger"]);
    expect(String(jsonBody(issue!).title)).toContain("Unrecognised cron trigger");
    expect(String(jsonBody(issue!).body)).toContain("13 4 * * *");
  });

  it("uses the missing-required label for a missing required cron", async () => {
    const { fetcher, calls } = recordingFetch();
    const verdict = checkTriggerContract([], {
      required: [
        {
          job: "twelve-x-session-catchup",
          cron: "52 * * * MON-FRI",
          reason: "The hourly backstop.",
          lost: "Every failed session day stays unrecovered.",
          evidence: "DIG-553 Finding 1, 543 runs",
        },
      ],
      jobs: [],
    });

    const results = await raiseVerdictAlarms(ENV, verdict, "the deployed trigger list", {
      fetcher,
    });

    expect(results[0].class).toBe(MISSING_REQUIRED_CRON);
    expect(results[0].raised).toBe(true);
    const issue = calls.at(-1);
    expect(jsonBody(issue!).labels).toEqual(["cron-missing-required-trigger"]);
    expect(jsonBody(issue!).body).toContain("Every failed session day stays unrecovered.");
    expect(jsonBody(issue!).body).toContain("DIG-553 Finding 1, 543 runs");
  });

  it("creates the class label when it is absent, in the twelve-x colour", async () => {
    const { fetcher, calls } = recordingFetch(404);
    const violation = unrecognisedCronViolation("13 4 * * *");

    await raiseViolationAlarms(ENV, [violation], "the deployed trigger list", { fetcher });

    const created = calls.find((call) => call.url.endsWith("/labels"));
    expect(created?.init.method).toBe("POST");
    expect(jsonBody(created!)).toMatchObject({
      name: "cron-unrecognised-trigger",
      color: ALARM_CLASSES[UNRECOGNISED_CRON].color,
    });
  });

  it("does not recreate a label that already exists", async () => {
    const { fetcher, calls } = recordingFetch(200);
    const violation = unrecognisedCronViolation("13 4 * * *");

    await raiseViolationAlarms(ENV, [violation], "the deployed trigger list", { fetcher });

    expect(calls.filter((call) => call.url.endsWith("/labels"))).toHaveLength(0);
  });

  it("sends the same headers the dispatch path sends, because it is the same token", async () => {
    const { fetcher, calls } = recordingFetch();
    await raiseViolationAlarms(ENV, [unrecognisedCronViolation("13 4 * * *")], "tick", {
      fetcher,
    });
    const headers = calls.at(-1)?.init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer github-token");
    expect(headers["X-GitHub-Api-Version"]).toBe("2022-11-28");
    expect(headers.Accept).toBe("application/vnd.github+json");
  });

  it("reports absence instead of throwing when the token is missing", async () => {
    const { fetcher, calls } = recordingFetch();
    const results = await raiseViolationAlarms(
      { DRY_RUN: "0" },
      [unrecognisedCronViolation("13 4 * * *")],
      "tick",
      { fetcher },
    );

    expect(results[0].raised).toBe(false);
    expect(results[0].error).toContain("GH_DISPATCH_TOKEN");
    expect(calls).toHaveLength(0);
  });

  it("reports absence instead of throwing when GitHub rejects the issue", async () => {
    const { fetcher } = recordingFetch(200, 422);
    const results = await raiseViolationAlarms(
      ENV,
      [unrecognisedCronViolation("13 4 * * *")],
      "tick",
      { fetcher },
    );

    expect(results[0].raised).toBe(false);
    expect(results[0].error).toContain("HTTP 422");
  });

  it("reports absence instead of throwing when the network fails", async () => {
    const fetcher = (async () => {
      throw new Error("network down");
    }) as unknown as typeof fetch;
    const results = await raiseViolationAlarms(
      ENV,
      [unrecognisedCronViolation("13 4 * * *")],
      "tick",
      { fetcher },
    );

    expect(results[0].raised).toBe(false);
    expect(results[0].error).toBe("network down");
  });
});

describe("the flood-stop: one issue per occurrence of drift, not per tick", () => {
  it("does not open a second issue for a drift that is already on the board", async () => {
    // The realistic flood: an unmapped `19 */2 * * MON-FRI` fires six times a
    // day, so the tick re-detects the same drift over and over. The rendered
    // title is spelled out here rather than built from alarmTitle(), so this
    // asserts what a reader sees on the issue, not what the code composes.
    const { fetcher, calls } = recordingFetch(200, 201, [
      {
        title: "Unrecognised cron trigger — 19 */2 * * MON-FRI",
        html_url: `https://github.com/${ALERT_REPO}/issues/4242`,
      },
    ]);

    const results = await raiseViolationAlarms(
      ENV,
      [unrecognisedCronViolation("19 */2 * * MON-FRI")],
      "the deployed trigger list, at the tick that fired",
      { fetcher },
    );

    expect(results[0].raised).toBe(false);
    expect(results[0].duplicate).toBe(true);
    expect(results[0].issue).toBe(`https://github.com/${ALERT_REPO}/issues/4242`);
    expect(results[0].error).toBeUndefined();
    // The one thing it must never do is comment on the open issue.
    const comments = calls.filter(
      (call) => call.init.method === "POST" && String(call.url).includes("/issues?"),
    );
    expect(comments).toHaveLength(0);
    const created = calls.filter((call) => call.url.endsWith("/issues"));
    expect(created).toHaveLength(0);
  });

  it("still opens an issue when the open one reports a different drift", async () => {
    const { fetcher, calls } = recordingFetch(200, 201, [
      {
        title: "Unrecognised cron trigger — 19 */2 * * MON-FRI",
        html_url: `https://github.com/${ALERT_REPO}/issues/4242`,
      },
    ]);

    const results = await raiseViolationAlarms(
      ENV,
      [unrecognisedCronViolation("13 4 * * *")],
      "the deployed trigger list, at the tick that fired",
      { fetcher },
    );

    expect(results[0].raised).toBe(true);
    expect(results[0].duplicate).toBeUndefined();
    expect(calls.filter((call) => call.url.endsWith("/issues"))).toHaveLength(1);
  });

  it("searches by the class label, and open only", async () => {
    const { fetcher, calls } = recordingFetch();
    await raiseViolationAlarms(ENV, [unrecognisedCronViolation("13 4 * * *")], "tick", {
      fetcher,
    });

    const search = calls.find((call) => String(call.url).includes("/issues?"));
    expect(search?.url).toContain("state=open");
    expect(search?.url).toContain("labels=cron-unrecognised-trigger");
  });

  it("raises anyway when the open-issue search fails, because a duplicate beats a silence", async () => {
    const inner = recordingFetch();
    const flaky = vi.fn(async (url: string, init: RequestInit = {}) => {
      if (String(url).includes("/issues?")) return new Response("boom", { status: 500 });
      return inner.fetcher(url, init);
    }) as unknown as typeof fetch;

    const results = await raiseViolationAlarms(
      ENV,
      [unrecognisedCronViolation("13 4 * * *")],
      "tick",
      { fetcher: flaky },
    );

    expect(results[0].raised).toBe(true);
    expect(results[0].duplicate).toBeUndefined();
  });

  it("raises anyway when the search answers with something that is not a list", async () => {
    const inner = recordingFetch();
    const odd = vi.fn(async (url: string, init: RequestInit = {}) => {
      if (String(url).includes("/issues?")) return Response.json({ message: "Not Found" }, { status: 200 });
      return inner.fetcher(url, init);
    }) as unknown as typeof fetch;

    const results = await raiseViolationAlarms(
      ENV,
      [unrecognisedCronViolation("13 4 * * *")],
      "tick",
      { fetcher: odd },
    );

    expect(results[0].raised).toBe(true);
    expect(results[0].error).toBeUndefined();
  });
});

describe("alarmsFor", () => {
  it("makes no alarm for a satisfied verdict", () => {
    // Narrowed to one contract row so this case is about the alarm mapping, not
    // about whether the repo's job map is intact — that is trigger-contract.test.ts.
    const verdict = checkTriggerContract(["7 0 * * MON-FRI"], {
      required: REQUIRED_TRIGGERS.filter((trigger) => trigger.job === "twelve-x-asia"),
    });
    expect(verdict.ok).toBe(true);
    expect(alarmsForVerdict(verdict, "the deployed trigger list")).toEqual([]);
  });

  it("keeps one occurrence per class, however many triggers broke", () => {
    const verdict = checkTriggerContract([]);
    const alarms = alarmsForVerdict(verdict, "the deployed trigger list");
    expect(alarms).toHaveLength(1);
    expect(alarms[0].violations).toHaveLength(verdict.missing.length);
  });
});