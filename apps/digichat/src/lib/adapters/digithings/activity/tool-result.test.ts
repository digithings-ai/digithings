import { describe, expect, it } from "vitest";
import { mapDigigraphTraceToSpans } from "./index";

describe("tool_result trace (generic MCP completion)", () => {
  it("maps a completed MCP tool_result to an execute_tool span with input + result", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "tool_result",
        payload: {
          tool: "datatap__list_connections",
          status: "completed",
          arguments: {},
          result: { connections: [{ name: "a", id: "1" }] },
        },
      },
      "full",
    );
    expect(spans).toHaveLength(1);
    expect(spans[0]).toMatchObject({
      operation: "execute_tool",
      status: "completed",
      toolName: "datatap__list_connections",
    });
    // Empty args object carries no keys — no toolInput, but the result
    // must survive so the row renders its Result pane as JSON.
    expect(spans[0]).not.toHaveProperty("toolInput");
    expect(spans[0]?.toolResult).toEqual({ connections: [{ name: "a", id: "1" }] });
  });

  it("keeps args and marks failed status through", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "tool_result",
        payload: {
          tool: "datatap__get_item",
          status: "failed",
          arguments: { itemId: "abc" },
          result: { error: "mcp_call_failed", tool: "get_item" },
        },
      },
      "labels",
    );
    expect(spans).toHaveLength(1);
    expect(spans[0]).toMatchObject({
      operation: "execute_tool",
      status: "failed",
      toolInput: { itemId: "abc" },
    });
    // labels gate must not withhold MCP results (unlike documents).
    expect(spans[0]?.toolResult).toEqual({ error: "mcp_call_failed", tool: "get_item" });
  });

  it("drops tool_result traces without a tool name", () => {
    expect(mapDigigraphTraceToSpans({ type: "tool_result", payload: {} }, "full")).toEqual([]);
  });
});
