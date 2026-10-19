import { describe, expect, it } from "vitest";
import {
  evaluateCatchup,
  evaluateFeedConfirm,
  evaluateHeartbeat,
  FEED_LOOKBACK_HOURS,
  runTwelvexWatch,
  sessionCatchupDue,
} from "./twelvex-watch";

const ok = (day: string) => ({ conclusion: "success", status: "completed", created_at: `${day}T08:00:00Z` });
// Tue 2026-10-13; window Fri 9, Mon 12 (Sat/Sun skipped)
const allPast = (extra: object[] = []) => [ok("2026-10-09"), ok("2026-10-12"), ...extra];

describe("evaluateCatchup", () => {
  it("skips when every due slot today and every past weekday is covered", () => {
    const now = Date.parse("2026-10-13T10:52:00Z");
    const v = evaluateCatchup(now, {
      asia: allPast([ok("2026-10-13")]),
      london: allPast([{ status: "in_progress", conclusion: null, created_at: "2026-10-13T07:12:00Z" }]),
      new_york: allPast(),
    });
    expect(v.due).toBe(false);
  });
  it("is due when a passed slot has no run today", () => {
    const now = Date.parse("2026-10-13T12:52:00Z");
    const v = evaluateCatchup(now, {
      asia: allPast([ok("2026-10-13")]),
      london: allPast([ok("2026-10-13")]),
      new_york: allPast(),
    });
    expect(v).toEqual({ due: true, reason: "new_york not covered 2026-10-13" });
  });
  it("is due when a past weekday failed", () => {
    const now = Date.parse("2026-10-13T00:52:00Z");
    const v = evaluateCatchup(now, {
      asia: allPast([ok("2026-10-13")]),
      london: [ok("2026-10-09"), { conclusion: "failure", status: "completed", created_at: "2026-10-12T07:12:00Z" }],
      new_york: allPast(),
    });
    expect(v.due).toBe(true);
  });
  it("counts catch-up fx- jobs and repair latches", () => {
    const now = Date.parse("2026-10-13T10:52:00Z");
    const v = evaluateCatchup(
      now,
      {
        asia: [ok("2026-10-09"), { conclusion: "failure", status: "completed", created_at: "2026-10-13T00:07:00Z" }],
        london: allPast([ok("2026-10-13")]),
        new_york: [ok("2026-10-12")],
      },
      { covered: { "2026-10-13": new Set(["asia"]) }, repaired: new Set(["2026-10-09"]) },
    );
    expect(v).toEqual({ due: true, reason: "asia not succeeded 2026-10-12" });
  });
  it("fails open when GitHub is unreadable", async () => {
    const v = await sessionCatchupDue(async () => new Response("x", { status: 502 }), "t", Date.now());
    expect(v.due).toBe(true);
  });
});

describe("watchdogs", () => {
  const now = Date.parse("2026-10-13T16:23:00Z");
  it("feed confirm: a succeeded run in 6h is silent", () => {
    expect(
      evaluateFeedConfirm(now, [
        { status: "completed", conclusion: "success", created_at: "2026-10-13T14:41:30Z" },
      ]).alarm,
    ).toBe(false);
  });
  // DIG-4381. GitHub reports a billing-blocked run as status=completed,
  // conclusion=failure: the run object completes while no job ever starts. The
  // old predicate filtered on `status === "completed"` and read this as healthy,
  // which is why the 16:23 watchdog stayed silent on 15, 16 and 19 October.
  it("feed confirm: completed + failure in 6h alarms", () => {
    const v = evaluateFeedConfirm(now, [
      {
        status: "completed",
        conclusion: "failure",
        created_at: "2026-10-13T14:41:30Z",
        html_url: "https://github.com/digithings-ai/twelve-x/actions/runs/1",
      },
    ]);
    expect(v.alarm).toBe(true);
    expect(v.reason).toBe("unsuccessful");
    // The detail must name the observed run, not just describe the rule: this is
    // the line an operator reads to see which run failed and why.
    expect(v.detail).toContain("`completed` / `failure`");
    expect(v.detail).toContain("https://github.com/digithings-ai/twelve-x/actions/runs/1");
  });
  it("feed confirm: reason separates none, unsuccessful and unreadable", () => {
    expect(evaluateFeedConfirm(now, []).reason).toBe("none");
    expect(evaluateFeedConfirm(now, [{ status: "completed", conclusion: "failure", created_at: "2026-10-13T14:41:30Z" }]).reason).toBe("unsuccessful");
    expect(evaluateFeedConfirm(now, null).reason).toBe("unreadable");
    expect(evaluateFeedConfirm(now, [{ status: "completed", conclusion: "success", created_at: "2026-10-13T14:41:30Z" }]).reason).toBe("confirmed");
  });
  it("feed confirm: the lookback boundary is inclusive", () => {
    const edge = "2026-10-13T10:23:00Z"; // exactly FEED_LOOKBACK_HOURS before `now`
    const justOutside = "2026-10-13T10:22:59Z";
    expect(FEED_LOOKBACK_HOURS).toBe(6);
    expect(evaluateFeedConfirm(now, [{ status: "completed", conclusion: "failure", created_at: edge }]).reason).toBe(
      "unsuccessful",
    );
    expect(evaluateFeedConfirm(now, [{ status: "completed", conclusion: "failure", created_at: justOutside }]).reason).toBe(
      "none",
    );
  });
  it("feed confirm: an unparseable created_at is not silently inside the window", () => {
    // A malformed timestamp must not read as confirmed, and must not count as a
    // run that started: an unreadable record is not evidence either way, so the
    // window alarms as "none" rather than passing.
    expect(evaluateFeedConfirm(now, [{ status: "completed", conclusion: "success", created_at: "not-a-date" }]).alarm).toBe(
      true,
    );
  });
  it("feed confirm: completed + failure beside a success in the window is silent", () => {
    expect(
      evaluateFeedConfirm(now, [
        { status: "completed", conclusion: "failure", created_at: "2026-10-13T14:41:30Z" },
        { status: "completed", conclusion: "success", created_at: "2026-10-13T12:00:00Z" },
      ]).alarm,
    ).toBe(false);
  });
  it("feed confirm: a success outside the window does not cover it", () => {
    expect(
      evaluateFeedConfirm(now, [
        { status: "completed", conclusion: "failure", created_at: "2026-10-13T14:41:30Z" },
        { status: "completed", conclusion: "success", created_at: "2026-10-13T08:00:00Z" },
      ]).alarm,
    ).toBe(true);
  });
  it("feed confirm: cancelled and neutral completions alarm too", () => {
    for (const conclusion of ["cancelled", "timed_out", "neutral", "skipped"]) {
      expect(
        evaluateFeedConfirm(now, [
          { status: "completed", conclusion, created_at: "2026-10-13T14:41:30Z" },
        ]).alarm,
      ).toBe(true);
    }
  });
  it("feed confirm: only a queued run alarms", () => {
    expect(evaluateFeedConfirm(now, [{ status: "queued", created_at: "2026-10-13T14:41:30Z" }]).alarm).toBe(true);
  });
  it("feed confirm: unreadable alarms", () => {
    expect(evaluateFeedConfirm(now, null).alarm).toBe(true);
  });

  // The verdict is only half the contract: an alarm that is computed and never
  // filed is still a silent watchdog. This drives runTwelvexWatch over a fake
  // GitHub so a blocked run has to reach the issue tracker.
  it("feed confirm: a blocked run files the alarm issue", async () => {
    const posted: string[] = [];
    const fetcher = async (input: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (input.includes("/actions/workflows/feed_published_confirm.yml/runs")) {
        return Response.json({
          workflow_runs: [
            {
              status: "completed",
              conclusion: "failure",
              created_at: "2026-10-13T14:41:30Z",
              id: 7,
              html_url: "https://github.com/digithings-ai/twelve-x/actions/runs/7",
            },
          ],
        });
      }
      if (input.endsWith("/labels/feed-confirm-silent") && method === "GET") {
        return new Response("nope", { status: 404 });
      }
      if (input.endsWith("/labels") && method === "POST") {
        return Response.json({});
      }
      if (input.includes("/issues?state=open") && method === "GET") {
        return Response.json([]);
      }
      if (input.endsWith("/issues") && method === "POST") {
        posted.push(String(init?.body));
        return Response.json({ html_url: "https://github.com/digithings-ai/twelve-x/issues/1" }, { status: 201 });
      }
      throw new Error(`unexpected request ${method} ${input}`);
    };

    const outcome = await runTwelvexWatch("feed-confirm", fetcher, "t", now);
    expect(outcome.alarm).toBe(true);
    expect(outcome.ok).toBe(true);
    expect(posted).toHaveLength(1);
    // The body must carry the *observed* run (from the fake API response), not
    // only the template's own words, or this test would pass on a stale template.
    expect(posted[0]).toContain("https://github.com/digithings-ai/twelve-x/actions/runs/7");
    expect(posted[0]).toContain("`completed` / `failure`");
    // A run that ran and failed must not be filed as one that never ran.
    expect(posted[0]).toContain("did not succeed");
    expect(posted[0]).not.toContain("did not run —");
  });
  it("heartbeat: 10h old is fine, 19h old alarms", () => {
    expect(evaluateHeartbeat(now, [{ created_at: "2026-10-13T06:03:00Z" }]).alarm).toBe(false);
    expect(evaluateHeartbeat(now, [{ created_at: "2026-10-12T21:00:00Z" }]).alarm).toBe(true);
    expect(evaluateHeartbeat(now, []).alarm).toBe(true);
  });
});
