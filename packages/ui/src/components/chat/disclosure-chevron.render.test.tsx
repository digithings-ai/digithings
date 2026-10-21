// @vitest-environment happy-dom
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { act, type FC } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { DigichatThread } from "./DigichatThread";

/**
 * Closed vs open for every collapsible row in one trace: the work chain,
 * the reasoning row, the tool-call group, and each tool row.
 */
const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

const TRACE: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      { type: "reasoning", text: "Checking both tools before answering." },
      {
        type: "tool-call",
        toolCallId: "t1",
        toolName: "digisearch",
        argsText: "{}",
        result: "ok",
      },
      {
        type: "tool-call",
        toolCallId: "t2",
        toolName: "digivault_search_notes",
        argsText: "{}",
        result: "ok",
      },
      { type: "text", text: "Both lookups landed." },
    ],
  },
];

type RowSlot =
  | "aui_work-chain-trigger"
  | "reasoning-trigger"
  | "tool-group-trigger"
  | "tool-fallback-trigger";

function chevron(trigger: Element): HTMLElement {
  const node = trigger.querySelector<HTMLElement>('[data-slot="disclosure-chevron"]');
  expect(node).toBeTruthy();
  expect(node!.className).not.toMatch(/-rotate-90|rotate-0|\bsize-4\b|\bsize-3\b/);
  const glyph = node!.querySelector<HTMLElement>('[data-slot="dot-matrix"]');
  expect(glyph?.getAttribute("data-state")).toBe("expand");
  expect(glyph?.className).toContain("!size-[0.55rem]");
  return node!;
}

async function mount() {
  const Harness: FC = () => {
    const runtime = useLocalRuntime(adapter, { initialMessages: TRACE });
    return (
      <AssistantRuntimeProvider runtime={runtime}>
        <DigichatThread placeholder="Ask digichat…" />
      </AssistantRuntimeProvider>
    );
  };
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness />);
  });
  return { host, unmount: () => act(() => root.unmount()) };
}

afterEach(() => {
  document.body.replaceChildren();
});

function expectClosed(host: HTMLElement, slot: RowSlot, min = 1) {
  const triggers = [...host.querySelectorAll(`[data-slot="${slot}"]`)];
  expect(triggers.length, slot).toBeGreaterThanOrEqual(min);
  for (const trigger of triggers) {
    expect(trigger.getAttribute("aria-expanded"), slot).toBe("false");
    expect(trigger.tagName).toBe("BUTTON");
    const node = chevron(trigger);
    expect(node.parentElement, slot).toBe(trigger);
  }
  return triggers as HTMLElement[];
}

async function openAll(host: HTMLElement, slot: RowSlot) {
  const closed = [
    ...host.querySelectorAll<HTMLElement>(`[data-slot="${slot}"][aria-expanded="false"]`),
  ];
  expect(closed.length, slot).toBeGreaterThan(0);
  for (const trigger of closed) {
    await act(async () => {
      trigger.click();
    });
    expect(trigger.getAttribute("aria-expanded"), slot).toBe("true");
    const node = chevron(trigger);
    expect(node.parentElement, slot).toBe(trigger);
    const root = trigger.closest("[data-state], [data-open]");
    const openByState =
      root?.getAttribute("data-state") === "open" || root?.hasAttribute("data-open");
    expect(openByState || trigger.getAttribute("aria-expanded") === "true", slot).toBe(true);
  }
}

describe("trace disclosure chevrons", () => {
  it("points each row from closed to open off the trigger's expanded state", async () => {
    const { host, unmount } = await mount();

    expectClosed(host, "aui_work-chain-trigger");
    await openAll(host, "aui_work-chain-trigger");

    expectClosed(host, "reasoning-trigger");
    expectClosed(host, "tool-group-trigger");
    expect(host.querySelector('[data-slot="tool-group-trigger-label"]')?.textContent).toContain(
      "2 tool calls",
    );
    await openAll(host, "reasoning-trigger");
    await openAll(host, "tool-group-trigger");

    expectClosed(host, "tool-fallback-trigger", 2);
    await openAll(host, "tool-fallback-trigger");

    unmount();
  });
});
