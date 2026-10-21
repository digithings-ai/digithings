import { describe, expect, it } from "vitest";

import { extractToolInvocationFailure, mapFoundryEvent, sanitizeUpstreamMessage } from "./stream";

/**
 * DIG-4459 chat transparency: the backend's own words reach the chat. Kept in
 * its own file so it does not collide with the capacity-retry suite (#6110).
 */
describe("foundry error pass-through (DIG-4459)", () => {
  it("carries a failed mcp_call's error as the tool result", () => {
    expect(
      mapFoundryEvent({
        type: "response.output_item.done",
        item: {
          type: "mcp_call",
          name: "get_collector_report_accounts",
          arguments: JSON.stringify({ reportId: "r-1", pageSize: 100 }),
          status: "failed",
          error: "Tool execution failed: 'pageSize' must be a string, but a number was provided.",
        },
      } as never),
    ).toMatchObject({
      type: "activity",
      span: {
        toolName: "get_collector_report_accounts",
        status: "failed",
        toolInput: { reportId: "r-1", pageSize: 100 },
        toolResult: {
          error: "Tool execution failed: 'pageSize' must be a string, but a number was provided.",
        },
      },
    });
  });

  it("reads an object error's message", () => {
    const mapped = mapFoundryEvent({
      type: "response.output_item.done",
      item: {
        type: "mcp_call",
        name: "t",
        arguments: "{}",
        status: "failed",
        error: { type: "mcp_tool_error", message: "Apollo 400: Variable $startDate got invalid value" },
      },
    } as never) as { span: { toolResult?: unknown } };
    expect(mapped.span.toolResult).toEqual({ error: "Apollo 400: Variable $startDate got invalid value" });
  });

  it("keeps a successful mcp_call untouched", () => {
    const mapped = mapFoundryEvent({
      type: "response.output_item.done",
      item: { type: "mcp_call", name: "t", arguments: "{}", output: '{"ok":true}' },
    } as never) as { span: { toolResult?: unknown; status: string } };
    expect(mapped.span).toMatchObject({ status: "completed", toolResult: { ok: true } });
  });

  it("keeps line breaks and long messages, strips links", () => {
    const long = `line one\nline two at https://internal.example/x\n${"x".repeat(1200)}`;
    const out = sanitizeUpstreamMessage(long);
    expect(out.split("\n")).toHaveLength(3);
    expect(out).toContain("[link]");
    expect(out).not.toContain("internal.example");
    expect(out.length).toBeGreaterThan(1200);
  });

  it("keeps a multi-line tool invocation failure whole", () => {
    const failure = extractToolInvocationFailure(
      "An error occurred invoking 'list_collector_reports': 'pageSize' must be a string.\n  at ToolArguments.validate",
    );
    expect(failure).toEqual({
      toolName: "list_collector_reports",
      errorText: "'pageSize' must be a string.\n at ToolArguments.validate",
    });
  });
});
