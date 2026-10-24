// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { act, type FC } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { DigichatThread } from "./DigichatThread";

/**
 * Closed vs open for every collapsible row in one trace: the work chain,
 * the reasoning row, the tool-call group, and each tool row. The caret is
 * the same pixel chevron as the user-message mark.
 */
const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

const TRACE: ThreadMessageLike[] = [
  {
    role: "user",
    content: [{ type: "text", text: "Look up both notes." }],
  },
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
  const matrix = node!.querySelector<HTMLElement>('[data-slot="dot-matrix"]');
  expect(matrix?.getAttribute("data-state")).toBe("user");
  expect(matrix?.className).toContain("!size-[0.55rem]");
  const glyph = matrix!.querySelector<SVGElement>('[data-slot="dot-matrix-grid"]');
  expect(glyph?.tagName.toLowerCase()).toBe("svg");
  expect(glyph?.parentElement).toBe(matrix);
  // Decorative (DIG-4669): the trigger is named by its visible text, so the
  // caret carries no name and adds nothing to the trigger's name.
  expect(matrix?.getAttribute("aria-hidden")).toBe("true");
  expect(matrix?.hasAttribute("role")).toBe(false);
  expect(matrix?.hasAttribute("aria-label")).toBe(false);
  expect(matrix?.textContent).toBe("");
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
  // The real sheets, so the rows below are checked by computed transform.
  const styles = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "styles");
  const style = document.createElement("style");
  style.textContent = ["chat-aui.css", "chat-digichat.css"]
    .map((f) => readFileSync(join(styles, f), "utf8"))
    .join("\n");
  document.head.append(style);
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness />);
  });
  return { host, unmount: () => act(() => root.unmount()) };
}

afterEach(() => {
  document.head.replaceChildren();
  document.body.replaceChildren();
});

function turn(node: HTMLElement): string {
  const grid = node.querySelector<SVGElement>('[data-slot="dot-matrix-grid"]')!;
  return getComputedStyle(grid).transform;
}

function expectClosed(host: HTMLElement, slot: RowSlot, min = 1) {
  const triggers = [...host.querySelectorAll(`[data-slot="${slot}"]`)];
  expect(triggers.length, slot).toBeGreaterThanOrEqual(min);
  for (const trigger of triggers) {
    expect(trigger.getAttribute("aria-expanded"), slot).toBe("false");
    expect(trigger.tagName).toBe("BUTTON");
    const node = chevron(trigger);
    expect(node.parentElement, slot).toBe(trigger);
    expect(turn(node), slot).not.toContain("rotate(90deg)");
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
    expect(turn(node), slot).toContain("rotate(90deg)");
  }
}

describe("trace disclosure chevrons", () => {
  it("points each row from closed to open off the trigger's expanded state", async () => {
    const { host, unmount } = await mount();

    const user = host.querySelector(
      '[data-slot="aui_user-message-root"] [data-slot="dot-matrix"][data-state="user"]',
    );
    expect(user?.className).toContain("size-3.5");
    expect(user?.closest('[data-slot="disclosure-chevron"]')).toBeNull();

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

    // Every open caret sits at one angle: the same rotate and origin on each
    // row's cube svg (chain, reasoning, group, and each tool row), and nothing
    // between that svg and the thread adds a turn of its own.
    const open = [...host.querySelectorAll<HTMLElement>('[aria-expanded="true"]')]
      .map((trigger) =>
        trigger.querySelector<HTMLElement>(':scope > [data-slot="disclosure-chevron"]'),
      )
      .filter((node): node is HTMLElement => node !== null);
    expect(open.length).toBe(5);
    const grids = open.map((node) =>
      node.querySelector<SVGElement>('[data-slot="dot-matrix-grid"]')!,
    );
    expect(new Set(grids.map((g) => getComputedStyle(g).transform))).toEqual(
      new Set(["rotate(90deg)"]),
    );
    expect(new Set(grids.map((g) => getComputedStyle(g).transformOrigin))).toEqual(
      new Set(["50% 50%"]),
    );
    for (const grid of grids) {
      for (let el = grid.parentElement; el && el !== host; el = el.parentElement) {
        const t = getComputedStyle(el).transform;
        expect(t === "" || t === "none", el.getAttribute("data-slot") ?? el.tagName).toBe(true);
      }
    }

    // No caret name leaks into the visible text or the accessibility tree.
    expect(host.querySelector('[data-slot="disclosure-chevron"] [aria-label]')).toBeNull();
    const tools = host.querySelector(
      '[data-slot="tool-group-trigger-loader"] [data-slot="dot-matrix-grid"]',
    );
    expect(tools).toBeTruthy();
    expect(tools!.closest('[data-slot="disclosure-chevron"]')).toBeNull();

    unmount();
  });

  it("turns only the icon, including a closed row inside an open chain", () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const styles = join(here, "..", "..", "styles");
    const style = document.createElement("style");
    style.textContent = [
      readFileSync(join(styles, "chat-aui.css"), "utf8"),
      readFileSync(join(styles, "chat-digichat.css"), "utf8"),
    ].join("\n");
    document.head.append(style);

    const caret = `
      <span data-slot="dot-matrix" data-state="user" aria-hidden="true">
        <svg data-slot="dot-matrix-grid"></svg>
      </span>
    `;
    const host = document.createElement("div");
    host.className = "digichat-thread";
    host.setAttribute("data-thread-skin", "digichat");
    host.innerHTML = `
      <div data-state="open" data-open>
        <button type="button" data-slot="aui_work-chain-trigger" aria-expanded="true" data-panel-open data-state="open">
          <span data-slot="aui_work-status-label">Worked</span>
          <span data-slot="disclosure-chevron">${caret}</span>
        </button>
        <button type="button" data-slot="tool-group-trigger" aria-expanded="true" data-panel-open data-state="open">
          <span data-slot="tool-group-trigger-label">2 tool calls</span>
          <span data-slot="disclosure-chevron">${caret}</span>
        </button>
        <button type="button" data-slot="tool-fallback-trigger" aria-expanded="false">
          <span data-slot="tool-fallback-trigger-label">digisearch</span>
          <span data-slot="disclosure-chevron">${caret}</span>
        </button>
      </div>
      <button type="button" data-slot="reasoning-trigger" aria-expanded="false">
        <span data-slot="reasoning-trigger-label">Reasoning</span>
        <span data-slot="disclosure-chevron">${caret}</span>
      </button>
    `;
    document.body.append(host);

    const flat = (value: string) =>
      value === "" || value === "none" || value === "matrix(1, 0, 0, 1, 0, 0)" ? "flat" : value;

    for (const slot of [
      "aui_work-chain-trigger",
      "tool-group-trigger",
      "tool-fallback-trigger",
      "reasoning-trigger",
    ]) {
      const trigger = host.querySelector(`[data-slot="${slot}"]`)!;
      const label = trigger.querySelector("span:not([data-slot='disclosure-chevron'])")!;
      const node = trigger.querySelector('[data-slot="disclosure-chevron"]')!;
      const matrix = node.querySelector('[data-slot="dot-matrix"]')!;
      const icon = node.querySelector('[data-slot="dot-matrix-grid"]')!;
      expect(flat(getComputedStyle(trigger).transform), slot).toBe("flat");
      expect(flat(getComputedStyle(label).transform), slot).toBe("flat");
      expect(flat(getComputedStyle(node).transform), slot).toBe("flat");
      expect(flat(getComputedStyle(matrix).transform), slot).toBe("flat");
      const open = trigger.getAttribute("aria-expanded") === "true";
      const iconTransform = getComputedStyle(icon).transform;
      if (open) {
        expect(["rotate(90deg)", "matrix(0, 1, -1, 0, 0, 0)"], slot).toContain(iconTransform);
      } else {
        expect(["rotate(0deg)", "none", "matrix(1, 0, 0, 1, 0, 0)", ""], slot).toContain(
          iconTransform,
        );
      }
    }

    style.remove();
    host.remove();
  });
});
