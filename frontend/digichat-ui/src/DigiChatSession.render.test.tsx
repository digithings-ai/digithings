/**
 * SSR smoke tests for the assistant turn's caret. The transcript shows exactly
 * one blinking block at a time, and which one it is carries meaning: the house
 * type-out while nothing has come back, the bare streaming caret once prose is
 * arriving, none at all when the turn is settled.
 *
 * Regression: waiting rendered BOTH — a <ChatStreamCursor> stacked above a
 * local "thinking …" row with three bouncing dots — so two indicators blinked
 * at once saying the same thing, and the dots' reduced-motion branch swapped
 * one infinite animation for another instead of settling.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DigiChatSession } from "./DigiChatSession";
import type { DigiChatMessage, DigiChatSessionProps } from "./types";

function sessionWith(messages: DigiChatMessage[], busy: boolean): string {
  const chat: DigiChatSessionProps["chat"] = {
    messages,
    busy,
    error: null,
    quotaPrompt: null,
    send: async () => {},
    stop: () => {},
    onRetry: () => {},
    modelLabel: "test-model",
  };
  return renderToStaticMarkup(<DigiChatSession chat={chat} showIntro={false} />);
}

/** The typed line's frame — present only when the step loader is mounted. */
const STEP_LINE = "tl-line";
/** The bare streaming caret digichat dresses with .dt-cur. */
const STREAM_CARET = "dt-cur";

describe("assistant turn — waiting", () => {
  const waiting: DigiChatMessage[] = [
    { role: "user", content: "how does auth work" },
    { role: "assistant", content: "" },
  ];

  it("shows the step loader when no prose and no tool chain have arrived", () => {
    const html = sessionWith(waiting, true);
    expect(html).toContain(STEP_LINE);
  });

  it("shows only ONE caret while waiting, not the loader plus a stream caret", () => {
    const html = sessionWith(waiting, true);
    expect(html).toContain(STEP_LINE);
    expect(html).not.toContain(STREAM_CARET);
  });

  it("keeps the first step readable with scripts off", () => {
    const html = sessionWith(waiting, true);
    // The label is typed imperatively, so <noscript> carries the first step.
    expect(html).toContain("<noscript>");
    expect(html).toContain("thinking");
  });
});

describe("assistant turn — past the wait", () => {
  it("drops the step loader for the bare caret once prose is streaming", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        { role: "assistant", content: "Auth uses RS256." },
      ],
      true,
    );
    expect(html).toContain(STREAM_CARET);
    expect(html).not.toContain(STEP_LINE);
  });

  it("drops the step loader once a tool chain is on screen, even with no prose", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        {
          role: "assistant",
          content: "",
          activities: [{ kind: "tool_call", name: "digivault.search", query: "auth" }],
        },
      ],
      true,
    );
    expect(html).not.toContain(STEP_LINE);
  });

  it("shows no caret at all when the turn is settled", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        { role: "assistant", content: "Done." },
      ],
      false,
    );
    expect(html).not.toContain(STEP_LINE);
    expect(html).not.toContain(STREAM_CARET);
  });
});
