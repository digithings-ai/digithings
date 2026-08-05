import { describe, it, expect } from "vitest";
import { mapDigivaultNdjsonEvent } from "./digivault-ndjson-adapter";

describe("mapDigivaultNdjsonEvent", () => {
  it("maps CF NDJSON kinds onto activity/text events", () => {
    expect(mapDigivaultNdjsonEvent({ type: "status", message: "Thinking…" })).toEqual({
      type: "activity",
      span: { operation: "chat", status: "started", label: "Thinking…" },
    });
    expect(
      mapDigivaultNdjsonEvent({ type: "tool_call", name: "search_digivault", query: "ports" }),
    ).toEqual({
      type: "activity",
      span: {
        operation: "execute_tool",
        status: "started",
        label: "Searching digivault…",
        toolName: "search_digivault",
        query: "ports",
      },
    });
    expect(
      mapDigivaultNdjsonEvent({
        type: "tool_result",
        name: "search_digivault",
        query: "ports",
        hits: [{ title: "A", path: "a.md" }],
        count: 1,
      }),
    ).toMatchObject({
      type: "activity",
      span: { operation: "retrieve", status: "completed", toolName: "search_digivault" },
    });
    expect(mapDigivaultNdjsonEvent({ type: "reasoning", delta: "…" })).toEqual({
      type: "activity",
      span: {
        operation: "chat",
        status: "started",
        label: "reasoning",
        reasoningDelta: "…",
      },
    });
    expect(mapDigivaultNdjsonEvent({ type: "content", delta: "Hi" })).toEqual({
      type: "text-delta",
      delta: "Hi",
    });
    expect(mapDigivaultNdjsonEvent({ type: "quota_exhausted", message: "out" })).toEqual({
      type: "quota_exhausted",
      message: "out",
    });
    expect(mapDigivaultNdjsonEvent({ type: "done" })).toEqual({ type: "done" });
  });
});
