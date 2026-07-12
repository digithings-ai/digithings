import { describe, it, expect } from "vitest";
import type { UIMessage } from "ai";
import { uiMessageToDigiChat } from "./use-embed-digi-chat";

function tracePart(label: string, status: string, id: string) {
  return {
    type: "data-digigraphTrace" as const,
    id,
    data: { v: 1, type: "external_activity", payload: { label, status } },
  };
}

function assistantMessage(parts: UIMessage["parts"]): UIMessage {
  return { id: "m1", role: "assistant", parts } as UIMessage;
}

describe("uiMessageToDigiChat trace de-duplication", () => {
  it("collapses repeated identical trace labels into one activity", () => {
    const msg = assistantMessage([
      tracePart("Searching DataTapStream docs…", "in_progress", "relay-trace-0"),
      tracePart("Searching DataTapStream docs…", "in_progress", "relay-trace-1"),
    ]);

    const { activities } = uiMessageToDigiChat(msg);

    expect(activities).toEqual([
      { kind: "trace", label: "Searching DataTapStream docs…", done: false },
    ]);
  });

  it("marks a collapsed step done if any frame for that label completed", () => {
    const msg = assistantMessage([
      tracePart("Searching DataTapStream docs…", "in_progress", "relay-trace-0"),
      tracePart("Searching DataTapStream docs…", "completed", "relay-trace-1"),
    ]);

    const { activities } = uiMessageToDigiChat(msg);

    expect(activities).toEqual([
      { kind: "trace", label: "Searching DataTapStream docs…", done: true },
    ]);
  });

  it("keeps distinct labels as separate steps in first-seen order", () => {
    const msg = assistantMessage([
      tracePart("Searching DataTapStream docs…", "in_progress", "relay-trace-0"),
      tracePart("Reading results…", "in_progress", "relay-trace-1"),
      tracePart("Searching DataTapStream docs…", "in_progress", "relay-trace-2"),
    ]);

    const { activities } = uiMessageToDigiChat(msg);

    expect(activities?.map((a) => a.kind === "trace" && a.label)).toEqual([
      "Searching DataTapStream docs…",
      "Reading results…",
    ]);
  });

  it("joins text parts and leaves activities undefined when no traces", () => {
    const msg = assistantMessage([
      { type: "text", text: "Hello " },
      { type: "text", text: "world" },
    ] as UIMessage["parts"]);

    const result = uiMessageToDigiChat(msg);

    expect(result.content).toBe("Hello world");
    expect(result.activities).toBeUndefined();
  });
});
