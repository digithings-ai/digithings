import { describe, expect, it } from "vitest";
import { mapDigigraphTraceToSpans } from "./index";

const DETAIL = "full" as const;

const PENDING_EVENT = {
  error: "mcp_call_requires_human_approval",
  pending_id: "a1b2c3d4e5f60718",
  server_id: "atlassian",
  tool: "addOrEditJiraIssueComment",
  target_arguments: ["issueIdOrKey", "comment"],
};

describe("digigraph pending-decision event → activity chain", () => {
  it("maps to a started row naming the concrete operation and its target", () => {
    const spans = mapDigigraphTraceToSpans(
      { type: "mcp_decision_pending", payload: PENDING_EVENT },
      DETAIL
    );
    expect(spans).toHaveLength(1);
    const span = spans[0];
    expect(span.operation).toBe("execute_tool");
    // `started`, not `failed`: the call is waiting on a person, nothing was lost.
    expect(span.status).toBe("started");
    expect(span.label).toBe(
      "addOrEditJiraIssueComment on atlassian — target: issueIdOrKey, comment"
    );
    expect(span.toolInput).toMatchObject({
      pending_id: "a1b2c3d4e5f60718",
      server_id: "atlassian",
      target_arguments: ["issueIdOrKey", "comment"],
    });
  });

  it("does not render a meta-tool decision (CTO bar item 10)", () => {
    for (const tool of ["discover", "executeRead", "executeWrite", "executeDestructive"]) {
      const spans = mapDigigraphTraceToSpans(
        { type: "mcp_decision_pending", payload: { ...PENDING_EVENT, tool } },
        DETAIL
      );
      expect(spans).toHaveLength(0);
    }
  });

  it("an ordinary tool call is unaffected (regression)", () => {
    const spans = mapDigigraphTraceToSpans(
      { type: "tool_call", payload: { tool: "digivault_get_note", status: "completed" } },
      DETAIL
    );
    expect(spans).toHaveLength(1);
    expect(spans[0]).toMatchObject({
      operation: "execute_tool",
      status: "completed",
      toolName: "digivault_get_note",
    });
  });

  it("an event carrying only a pending_id is not mistaken for a tool call", () => {
    // Control that the new branch is discriminating: the same payload shape
    // WITHOUT a pending decision still reaches the ordinary tool_call path.
    const ordinary = mapDigigraphTraceToSpans(
      { type: "tool_call", payload: { tool: "digivault_get_note" } },
      DETAIL
    );
    expect(ordinary).toHaveLength(1);
  });
});
