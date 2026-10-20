import { describe, expect, it } from "vitest";
import { decideAlert, labelFor, verdictLine } from "./alerts";

const NOW = Date.parse("2026-10-20T00:00:00Z");

describe("the reason a run failed", () => {
  it("reads the verdict line the pinned ingest prints on stdout", () => {
    const tail = [
      "$ python -m twelve_x.scripts.ingest_market_context intraday",
      "MARKET_CONTEXT_VERDICT=source: 2 source(s) failed: dmx-overview",
      "ERROR twelve_x.scripts.ingest_market_context: source: 2 source(s) failed: dmx-overview",
    ].join("\n");
    expect(verdictLine(tail)).toBe("source: 2 source(s) failed: dmx-overview");
  });

  it("reads the log marker when the pin prints no verdict line", () => {
    const tail = [
      "ERROR twelve_x.scripts.ingest_market_context: market_context: " +
        "source: could not establish a desk session: 401",
    ].join("\n");
    expect(verdictLine(tail)).toBe("source: could not establish a desk session: 401");
  });

  it("falls back to the last meaningful line, never to a placeholder", () => {
    expect(verdictLine("  dmx-overview   FAILED  upstream 500")).toBe(
      "dmx-overview FAILED upstream 500",
    );
    expect(verdictLine("")).toBe("no output was recorded");
    expect(verdictLine("nothing here")).not.toBe("no verdict line was recorded");
  });

  it("keeps the reason on one line and inside the alert limit", () => {
    const tail = `MARKET_CONTEXT_VERDICT=source: ${"x".repeat(900)}`;
    const reason = verdictLine(tail);
    expect(reason.length).toBe(400);
    expect(reason).not.toContain("\n");
  });
});

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
      reason: "source: supabase_url is required",
      logTail: "supabase_url is required",
      now: NOW,
      open: [],
    });
    expect(decision.action).toBe("create");
    if (decision.action !== "create") return;
    expect(decision.body).toContain("Reason: source: supabase_url is required");
    expect(decision.body).toContain("Log tail");
    expect(decision.body).toContain("supabase_url is required");
  });

  it("carries the log tail on a repeat occurrence", () => {
    const decision = decideAlert({
      route: "ingest",
      exitCode: 1,
      bucket: "intraday",
      reason: "source: 401 Unauthorized",
      logTail: "401 Unauthorized",
      now: NOW,
      open: [{ number: 12, createdAt: NOW - 1000, acknowledged: false }],
    });
    expect(decision.action).toBe("comment");
    if (decision.action !== "comment") return;
    expect(decision.body).toContain("Reason: source: 401 Unauthorized");
    expect(decision.body).toContain("Log tail");
    expect(decision.body).toContain("401 Unauthorized");
  });

  it("omits the log tail section when there is no tail", () => {
    const decision = decideAlert({
      route: "ingest",
      exitCode: 1,
      reason: "source: 401 Unauthorized",
      now: NOW,
      open: [],
    });
    expect(decision.action).toBe("create");
    if (decision.action !== "create") return;
    expect(decision.body).not.toContain("Log tail");
  });
});
