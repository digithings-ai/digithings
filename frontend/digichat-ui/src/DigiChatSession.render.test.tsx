/**
 * SSR smoke tests for the assistant turn's caret. The transcript shows exactly
 * one waiting indicator at a time, and which one it is carries meaning: the house
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
  /** Nothing has come back at all — the stream has named no step. */
  const waiting: DigiChatMessage[] = [
    { role: "user", content: "how does auth work" },
    { role: "assistant", content: "" },
  ];

  /** The stream has named a step; the caret has something true to say. */
  const withStep: DigiChatMessage[] = [
    { role: "user", content: "how does auth work" },
    {
      role: "assistant",
      content: "",
      activities: [{ kind: "trace", label: "Thinking", done: false }],
    },
  ];

  // With nothing to report, the caret claims nothing: a bare blink, no words.
  // It used to cycle a fixed script here regardless of what was happening.
  it("shows a bare cursor — not invented words — when the stream has said nothing", () => {
    const html = sessionWith(waiting, true);
    expect(html).toContain(STREAM_CARET);
    expect(html).not.toContain(STEP_LINE);
    for (const invented of ["thinking", "routing through", "gathering context", "composing"]) {
      expect(html.toLowerCase()).not.toContain(invented);
    }
  });

  it("types the REAL step once the stream names one", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        {
          role: "assistant",
          content: "",
          activities: [{ kind: "trace", label: "Thinking", done: false }],
        },
      ],
      true,
    );
    expect(html).toContain(STEP_LINE);
    expect(html).toContain("Thinking");
  });

  it("names the tool's own query while a search is in flight", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        {
          role: "assistant",
          content: "",
          activities: [{ kind: "tool_call", name: "azure_ai_search", query: "/api/config" }],
        },
      ],
      true,
    );
    expect(html).toContain('Searching for &quot;/api/config&quot;');
  });

  it("shows only ONE caret while waiting, never a step line plus a stream caret", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        {
          role: "assistant",
          content: "",
          activities: [{ kind: "trace", label: "Thinking", done: false }],
        },
      ],
      true,
    );
    expect(html).toContain(STEP_LINE);
    expect(html).not.toContain(STREAM_CARET);
  });

  it("keeps the live step readable with scripts off", () => {
    const html = sessionWith(
      [
        { role: "user", content: "hi" },
        {
          role: "assistant",
          content: "",
          activities: [{ kind: "trace", label: "Thinking", done: false }],
        },
      ],
      true,
    );
    // The label is typed imperatively, so <noscript> carries it.
    expect(html).toContain("<noscript>");
    expect(html).toContain("Thinking");
  });

  // Regression: the caret's screen-reader line used Tailwind's `.sr-only`, a
  // utility only emitted into an app whose own source uses the class. This app
  // is consumed by digithings-web, which never does — so the hidden span
  // rendered as ordinary visible text, printing the step word a second time
  // beside the one being typed. The class now ships with the component.
  it("hides the screen-reader line behind a class the component owns", () => {
    const html = sessionWith(withStep, true);
    expect(html).toContain('class="tl-sr"');
    expect(html).not.toContain("sr-only");
  });

  // Regression: role="status" is aria-live=polite, and its text was the step
  // label, which changes ~every 2.5s forever while uncontrolled. A screen
  // reader got four invented phrases on a loop for the length of the wait,
  // where the indicator this replaced announced one static line once.
  // The caret is now always caller-driven, so it announces the real step —
  // which is correct: a step that came off the stream IS progress, and the
  // "Working…" fallback exists for callers that have no step to give.
  it("announces the real step, since the session only ever supplies a real one", () => {
    const html = sessionWith(withStep, true);
    const status = html.match(/<span class="tl-sr" role="status">([^<]*)</)?.[1];
    expect(status).toBe("Thinking");
    expect(status).not.toContain("digigraph");
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

  // Superseded: a tool chain used to END the wait, which threw away the one
  // state where we can actually name what is happening. It now DRIVES it.
  it("keeps naming the step while a tool chain runs with no prose yet", () => {
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
    expect(html).toContain(STEP_LINE);
    expect(html).toContain('Searching for &quot;auth&quot;');
    // The chain renders too — the caret is the at-a-glance line above it.
    expect(html).toContain("dc-activities");
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
