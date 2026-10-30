// @vitest-environment happy-dom
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { act, type FC } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { BaseThread } from "./thread";
import { TraceLocaleProvider } from "../../trace-i18n";
import {
  chainRuns,
  chainStatus,
  chainStatusLabel,
  chainSummary,
} from "./elements/chain-of-thought-activity";

/**
 * Consecutive reasoning and tool calls fold into one assistant-ui Run
 * activity disclosure in the base skin. Mocked messages only.
 */
const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

const CHAIN_TURN: ThreadMessageLike[] = [
  { role: "user", content: [{ type: "text", text: "what are the opening hours?" }] },
  {
    role: "assistant",
    content: [
      { type: "reasoning", text: "The user wants opening hours; search the help centre." },
      {
        type: "tool-call",
        toolCallId: "t1",
        toolName: "web_search",
        args: { query: "opening hours" },
        argsText: '{"query":"opening hours"}',
        result: { results: [{ title: "Hours", url: "https://example.com/hours" }] },
      },
      {
        type: "tool-call",
        toolCallId: "t2",
        toolName: "web_fetch",
        args: { url: "https://example.com/hours" },
        argsText: '{"url":"https://example.com/hours"}',
        result: { text: "Open 9 to 5." },
      },
      { type: "reasoning", text: "The page says nine to five." },
      { type: "text", text: "We are open from 9:00 to 17:00." },
    ],
  },
];

const REASONING_ONLY: ThreadMessageLike[] = [
  { role: "user", content: [{ type: "text", text: "hi" }] },
  {
    role: "assistant",
    content: [
      { type: "reasoning", text: "A greeting." },
      { type: "text", text: "Hello!" },
    ],
  },
];

let cleanup: (() => void) | undefined;

/** Unmount the current root; a function so tsc does not narrow `cleanup` at call sites. */
function teardown(): void {
  cleanup?.();
  cleanup = undefined;
  document.body.innerHTML = "";
}
afterEach(teardown);

async function mount(initialMessages: ThreadMessageLike[], locale = "en") {
  const Harness: FC = () => {
    const runtime = useLocalRuntime(adapter, { initialMessages });
    return (
      <TraceLocaleProvider locale={locale}>
        <AssistantRuntimeProvider runtime={runtime}>
          <BaseThread />
        </AssistantRuntimeProvider>
      </TraceLocaleProvider>
    );
  };
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness />);
  });
  await act(async () => {});
  cleanup = () => act(() => root.unmount());
  return host;
}

const chainTrigger = (host: HTMLElement) =>
  host.querySelector<HTMLElement>(
    '[data-slot="run-activity"] [data-slot="collapsible-trigger"]',
  );

describe("base skin chain of thought", () => {
  it("folds consecutive reasoning and tool calls under one summary", async () => {
    const host = await mount(CHAIN_TURN);
    expect(host.querySelectorAll('[data-slot="run-activity"]')).toHaveLength(1);
    const trigger = chainTrigger(host);
    expect(trigger?.textContent).toContain("Thought and used 2 tools");
    expect(trigger?.getAttribute("aria-expanded")).toBe("false");
    // No separate reasoning / tool-group dropdowns.
    expect(host.querySelector('[data-slot="tool-group-trigger"]')).toBeNull();
    expect(host.querySelector(".aui-reasoning-trigger")).toBeNull();
    // The answer stays outside the disclosure.
    expect(host.textContent).toContain("We are open from 9:00 to 17:00.");
  });

  it("expands to the reasoning and tool calls in order", async () => {
    const host = await mount(CHAIN_TURN);
    await act(async () => chainTrigger(host)!.click());
    expect(chainTrigger(host)?.getAttribute("aria-expanded")).toBe("true");
    const items = [
      ...host.querySelectorAll<HTMLElement>('[data-slot="run-activity"] li'),
    ];
    expect(items.map((li) => li.dataset.activityKind)).toEqual([
      "commentary",
      "tool",
      "commentary",
    ]);
    expect(items[0]!.textContent).toContain("search the help centre");
    expect(items[1]!.querySelectorAll('[data-slot="tool-fallback-trigger"]')).toHaveLength(2);
    expect(items[1]!.textContent).toContain("web_search");
    expect(items[1]!.textContent).toContain("web_fetch");
    expect(items[2]!.textContent).toContain("nine to five");
  });

  it("says Thought when the chain is reasoning only", async () => {
    const host = await mount(REASONING_ONLY);
    expect(chainTrigger(host)?.textContent).toContain("Thought");
    expect(chainTrigger(host)?.textContent).not.toContain("tool");
  });
});

describe("chain summary helpers", () => {
  const parts = [
    { type: "reasoning" },
    { type: "tool-call", toolName: "web_search" },
    { type: "tool-call", toolName: "web_fetch" },
    { type: "reasoning" },
    { type: "text" },
  ];

  it("splits the chain into reasoning and tool runs", () => {
    expect(chainRuns(parts, [0, 1, 2, 3])).toEqual([
      { kind: "reasoning", indices: [0] },
      { kind: "tool", indices: [1, 2], toolNames: ["web_search", "web_fetch"] },
      { kind: "reasoning", indices: [3] },
    ]);
  });

  it("summarises what the chain did", () => {
    expect(chainSummary(chainRuns(parts, [0, 1, 2, 3]))).toBe("Thought and used 2 tools");
    expect(chainSummary(chainRuns(parts, [1]))).toBe("Used 1 tool");
    expect(chainSummary(chainRuns(parts, [0]))).toBe("Thought");
  });

  it("maps the run status and labels the live step", () => {
    expect(chainStatus(true, { type: "running" })).toBe("running");
    expect(chainStatus(false, { type: "running" })).toBe("complete");
    expect(chainStatus(false, { type: "incomplete", reason: "cancelled" })).toBe("cancelled");
    expect(chainStatus(false, { type: "incomplete", reason: "error" })).toBe("error");
    expect(chainStatusLabel("running", chainRuns(parts, [0, 1]))).toBe("Working");
    expect(chainStatusLabel("running", chainRuns(parts, [0]))).toBe("Thinking");
    expect(chainStatusLabel("cancelled", chainRuns(parts, [1]))).toBe("Stopped · Used 1 tool");
  });
});

describe("trace strings follow the session language", () => {
  it("EN and FR summary, tool rows and reasoning-only chains", async () => {
    for (const [locale, summary, toolRow, thought] of [
      ["en", "Thought and used 2 tools", "Used tool", "Thought"],
      ["fr", "Réflexion et 2 outils utilisés", "Outil utilisé", "Réflexion terminée"],
    ] as const) {
      const host = await mount(CHAIN_TURN, locale);
      const trigger = host.querySelector<HTMLElement>('[data-slot="run-activity"] [data-slot="collapsible-trigger"]')!;
      expect(trigger.textContent?.trim()).toBe(summary);
      await act(async () => trigger.click());
      await act(async () => {});
      const rows = [...host.querySelectorAll('[data-slot="tool-fallback-trigger"]')].map((el) => el.textContent ?? "");
      expect(rows.length).toBe(2);
      for (const row of rows) expect(row).toContain(toolRow);
      teardown();
      const only = await mount(REASONING_ONLY, locale);
      expect(
        only.querySelector('[data-slot="run-activity"] [data-slot="collapsible-trigger"]')?.textContent?.trim(),
      ).toBe(thought);
      teardown();
    }
  });
});
