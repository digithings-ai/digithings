import { describe, expect, it } from "vitest";
import { decideAlert, labelFor } from "./alerts";

const NOW = Date.parse("2026-10-20T00:00:00Z");

describe("alert body", () => {
  it("files an FX research failure under the label the workflow uses", () => {
    expect(labelFor("session", 1)).toBe("daily-run-failure");
    expect(labelFor("session", 0)).toBeNull();
    const decision = decideAlert({
      route: "session",
      exitCode: 1,
      session: "asia",
      reason: "the graph stopped",
      logTail: "the last line the run said",
      now: 0,
      open: [],
    });
    expect(decision).toMatchObject({ action: "create", label: "daily-run-failure" });
    expect(decision.action === "create" && decision.title).toContain("FX research run failed");
    expect(decision.action === "create" && decision.body).toContain("session 'asia'");
  });
  it("carries the log tail on a new failure so the run names its cause", () => {
    const decision = decideAlert({
      route: "ingest",
      exitCode: 1,
      bucket: "intraday",
      reason: "no verdict line was recorded",
      logTail: "supabase_url is required",
      now: NOW,
      open: [],
    });
    expect(decision.action).toBe("create");
    if (decision.action !== "create") return;
    expect(decision.body).toContain("Log tail");
    expect(decision.body).toContain("supabase_url is required");
  });

  it("carries the log tail on a repeat occurrence", () => {
    const decision = decideAlert({
      route: "ingest",
      exitCode: 1,
      bucket: "intraday",
      reason: "no verdict line was recorded",
      logTail: "401 Unauthorized",
      now: NOW,
      open: [{ number: 12, createdAt: NOW - 1000, acknowledged: false }],
    });
    expect(decision.action).toBe("comment");
    if (decision.action !== "comment") return;
    expect(decision.body).toContain("Log tail");
    expect(decision.body).toContain("401 Unauthorized");
  });

  it("omits the log tail section when there is no tail", () => {
    const decision = decideAlert({
      route: "ingest",
      exitCode: 1,
      reason: "no verdict line was recorded",
      now: NOW,
      open: [],
    });
    expect(decision.action).toBe("create");
    if (decision.action !== "create") return;
    expect(decision.body).not.toContain("Log tail");
  });
});
