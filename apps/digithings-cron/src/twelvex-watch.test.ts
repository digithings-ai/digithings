import { describe, expect, it } from "vitest";
import {
  evaluateCatchup,
  evaluateFeedConfirm,
  evaluateHeartbeat,
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
  it("feed confirm: completed run in 6h is silent", () => {
    expect(evaluateFeedConfirm(now, [{ status: "completed", created_at: "2026-10-13T14:41:30Z" }]).alarm).toBe(false);
  });
  it("feed confirm: only a queued run alarms", () => {
    expect(evaluateFeedConfirm(now, [{ status: "queued", created_at: "2026-10-13T14:41:30Z" }]).alarm).toBe(true);
  });
  it("feed confirm: unreadable alarms", () => {
    expect(evaluateFeedConfirm(now, null).alarm).toBe(true);
  });
  it("heartbeat: 10h old is fine, 19h old alarms", () => {
    expect(evaluateHeartbeat(now, [{ created_at: "2026-10-13T06:03:00Z" }]).alarm).toBe(false);
    expect(evaluateHeartbeat(now, [{ created_at: "2026-10-12T21:00:00Z" }]).alarm).toBe(true);
    expect(evaluateHeartbeat(now, []).alarm).toBe(true);
  });
});
