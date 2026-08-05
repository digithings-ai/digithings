import { describe, it, expect, beforeEach } from "vitest";
import type { UIMessage } from "ai";
import { isEmbedTrialUnlockedAtSend, uiMessageToDigiChat } from "./use-embed-digi-chat";
import { ACTIVITY_PART_TYPE } from "@/lib/chat-activity";
import {
  resetLiveTrialUnlockedForTests,
  writeTrialUnlocked,
} from "@/lib/embed-gate";

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

describe("isEmbedTrialUnlockedAtSend", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    // @ts-expect-error — minimal localStorage for the helper under test
    globalThis.localStorage = {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
    };
    resetLiveTrialUnlockedForTests();
  });

  it("is false when nothing has unlocked this host", () => {
    expect(isEmbedTrialUnlockedAtSend("https://datatap.stream")).toBe(false);
  });

  it("reads unlock written after the frozen transport was created", () => {
    // Simulates: transport closed over trialUnlocked=false, then parent posted
    // datatap:unlocked which called writeTrialUnlocked.
    expect(isEmbedTrialUnlockedAtSend("https://datatap.stream", false)).toBe(false);
    writeTrialUnlocked("https://datatap.stream", true);
    expect(isEmbedTrialUnlockedAtSend("https://datatap.stream", false)).toBe(true);
  });

  it("honors an explicit prop fallback when storage is empty", () => {
    expect(isEmbedTrialUnlockedAtSend("https://datatap.stream", true)).toBe(true);
  });
});

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

const activityPart = (data: unknown) => ({ type: ACTIVITY_PART_TYPE, data });

describe("uiMessageToDigiChat activity parts", () => {
  it("projects activity spans into rich rows", () => {
    const msg = {
      id: "a1",
      role: "assistant",
      parts: [
        { type: "text", text: "Here you go." },
        activityPart({
          operation: "retrieve",
          toolName: "file_search",
          query: "auth",
          status: "completed",
          label: "Sources",
          documents: [{ title: "Auth", path: "https://x/auth" }],
        }),
      ],
    } as unknown as UIMessage;

    expect(uiMessageToDigiChat(msg)).toEqual({
      role: "assistant",
      content: "Here you go.",
      activities: [
        {
          kind: "tool_result",
          name: "file_search",
          query: "auth",
          hits: [{ title: "Auth", path: "https://x/auth" }],
          count: 1,
        },
      ],
    });
  });

  // The allowlist has to hold at the client boundary too, not only at the writer.
  it("drops a malformed span rather than rendering it", () => {
    const msg = {
      id: "a2",
      role: "assistant",
      parts: [{ type: "text", text: "hi" }, activityPart({ operation: "exfiltrate" })],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toBeUndefined();
  });

  // Compatibility window: a page cached across a deploy still speaks the old part.
  it("still renders a legacy digigraphTrace part when no activity parts are present", () => {
    const msg = {
      id: "a3",
      role: "assistant",
      parts: [
        { type: "text", text: "hi" },
        {
          type: "data-digigraphTrace",
          data: { v: 1, type: "external_activity", payload: { label: "Planning", status: "completed" } },
        },
      ],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toEqual([
      { kind: "trace", label: "Planning", done: true },
    ]);
  });

  // Activity parts win outright — a mid-stream deploy must not double-render.
  it("ignores legacy trace parts when activity parts are present", () => {
    const msg = {
      id: "a4",
      role: "assistant",
      parts: [
        { type: "text", text: "hi" },
        activityPart({ operation: "chat", status: "completed", label: "New" }),
        {
          type: "data-digigraphTrace",
          data: { v: 1, type: "external_activity", payload: { label: "Old", status: "completed" } },
        },
      ],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toEqual([
      { kind: "trace", label: "New", done: true },
    ]);
  });

  // When both legacy trace and activity parts appear in one message (e.g. rolling
  // deploy), activity parts win — the embed hook must render that step once.
  it("renders a step once, not twice, when the same step arrives as both a legacy and an activity part", () => {
    const msg = {
      id: "a6",
      role: "assistant",
      parts: [
        { type: "text", text: "hi" },
        activityPart({ operation: "chat", status: "completed", label: "Searching…" }),
        {
          type: "data-digigraphTrace",
          data: { v: 1, type: "external_activity", payload: { label: "Searching…", status: "completed" } },
        },
      ],
    } as unknown as UIMessage;
    const { activities } = uiMessageToDigiChat(msg);
    expect(activities).toEqual([{ kind: "trace", label: "Searching…", done: true }]);
    expect(activities).toHaveLength(1);
  });

  // Discriminating case: even when all activity spans are malformed, the presence of activity
  // parts gates out the legacy trace. A count-based gate would incorrectly fall back to legacy.
  it("ignores legacy trace even when all activity parts are malformed", () => {
    const msg = {
      id: "a5",
      role: "assistant",
      parts: [
        { type: "text", text: "hi" },
        activityPart({ operation: "exfiltrate" }),
        {
          type: "data-digigraphTrace",
          data: { v: 1, type: "external_activity", payload: { label: "Legacy", status: "completed" } },
        },
      ],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toBeUndefined();
  });
});
