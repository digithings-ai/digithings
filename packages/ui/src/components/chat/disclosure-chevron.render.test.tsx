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
  expect(node!.querySelector('[data-slot="dot-matrix"]')).toBeNull();
  const glyph = node!.querySelector<SVGElement>('[data-slot="disclosure-chevron-icon"]');
  expect(glyph?.tagName.toLowerCase()).toBe("svg");
  expect(glyph?.parentElement).toBe(node);
  const name = node!.querySelector<HTMLElement>('[data-slot="screen-reader-name"]');
  expect(name).toBeTruthy();
  expect(name!.style.position).toBe("absolute");
  expect(name!.style.width).toBe("1px");
  expect(name!.style.height).toBe("1px");
  expect(name!.style.overflow).toBe("hidden");
  expect(name!.style.clipPath).toBe("inset(50%)");
  expect(name!.style.left).toBe("");
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

    const names = host.querySelectorAll<HTMLElement>('[data-slot="screen-reader-name"]');
    expect(names.length).toBeGreaterThan(0);
    for (const name of names) {
      expect(name.style.position).toBe("absolute");
      expect(name.style.width).toBe("1px");
      expect(name.style.left).toBe("");
    }
    const tools = host.querySelector('[data-slot="tool-group-trigger-loader"] [data-slot="dot-matrix-grid"]');
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

    const host = document.createElement("div");
    host.className = "digichat-thread";
    host.setAttribute("data-thread-skin", "digichat");
    host.innerHTML = `
      <div data-state="open" data-open>
        <button type="button" data-slot="aui_work-chain-trigger" aria-expanded="true" data-panel-open data-state="open">
          <span data-slot="aui_work-status-label">Worked</span>
          <span data-slot="disclosure-chevron">
            <svg data-slot="disclosure-chevron-icon"></svg>
            <span data-slot="screen-reader-name">Toggle the work</span>
          </span>
        </button>
        <button type="button" data-slot="tool-group-trigger" aria-expanded="true" data-panel-open data-state="open">
          <span data-slot="tool-group-trigger-label">2 tool calls</span>
          <span data-slot="disclosure-chevron">
            <svg data-slot="disclosure-chevron-icon"></svg>
            <span data-slot="screen-reader-name">Toggle tools</span>
          </span>
        </button>
        <button type="button" data-slot="tool-fallback-trigger" aria-expanded="false">
          <span data-slot="tool-fallback-trigger-label">digisearch</span>
          <span data-slot="disclosure-chevron">
            <svg data-slot="disclosure-chevron-icon"></svg>
            <span data-slot="screen-reader-name">Toggle tool</span>
          </span>
        </button>
      </div>
      <button type="button" data-slot="reasoning-trigger" aria-expanded="false">
        <span data-slot="reasoning-trigger-label">Reasoning</span>
        <span data-slot="disclosure-chevron">
          <svg data-slot="disclosure-chevron-icon"></svg>
          <span data-slot="screen-reader-name">Toggle reasoning</span>
        </span>
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
      const chevron = trigger.querySelector('[data-slot="disclosure-chevron"]')!;
      const name = chevron.querySelector('[data-slot="screen-reader-name"]')!;
      const icon = chevron.querySelector('[data-slot="disclosure-chevron-icon"]')!;
      expect(flat(getComputedStyle(trigger).transform), slot).toBe("flat");
      expect(flat(getComputedStyle(label).transform), slot).toBe("flat");
      expect(flat(getComputedStyle(chevron).transform), slot).toBe("flat");
      expect(flat(getComputedStyle(name).transform), slot).toBe("flat");
      const nameStyle = getComputedStyle(name);
      expect(nameStyle.position, slot).toBe("absolute");
      expect(nameStyle.width, slot).toBe("1px");
      expect(nameStyle.height, slot).toBe("1px");
      expect(nameStyle.overflow, slot).toBe("hidden");
      expect(nameStyle.left, slot).not.toMatch(/^-?\d+px$/);
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
