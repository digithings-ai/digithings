// @vitest-environment happy-dom
/**
 * Private mode renders the work exactly like normal mode — the same "Worked"
 * chain, the same "N tool calls" group, the same rows, labels and icons, under
 * every view setting — and the only difference is that a private reasoning or
 * tool row never opens. Mocks only: a local runtime with fixed messages.
 */
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { DigichatThread, type GroupDisclosureMode } from "./DigichatThread";
import type { WorkVisibility } from "./stock/skin-types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

const MARK = "PAYLOAD-MARK";

/** What a normal session receives: reasoning text, arguments and results. */
const NORMAL: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      { type: "reasoning", text: `look up the queue (${MARK}-reasoning)` },
      {
        type: "tool-call",
        toolCallId: "t1",
        toolName: "search_tickets",
        argsText: JSON.stringify({ query: `${MARK}-args` }),
        result: { tickets: [`${MARK}-result`] },
      },
      {
        type: "tool-call",
        toolCallId: "t2",
        toolName: "get_ticket",
        argsText: JSON.stringify({ id: `${MARK}-args-2` }),
        result: { body: `${MARK}-result-2` },
      },
      { type: "text", text: "one open ticket" },
    ],
  },
];

/** What a private session receives after apps/digichat/src/lib/private-stream.ts. */
const PRIVATE: ThreadMessageLike[] = [
  {
    role: "assistant",
    content: [
      { type: "reasoning", text: "…" },
      { type: "tool-call", toolCallId: "p1", toolName: "search_tickets", argsText: "{}", result: {} },
      { type: "tool-call", toolCallId: "p2", toolName: "get_ticket", argsText: "{}", result: {} },
      { type: "text", text: "one open ticket" },
    ],
  },
];

type View = {
  name: string;
  workVisibility: WorkVisibility;
  reasoningMode: GroupDisclosureMode;
  toolCallsMode: GroupDisclosureMode;
};

// The product's view settings, folded the way apps/digichat/src/lib/view-modes.ts
// folds them, plus the per-group overrides and "off".
const VIEWS: View[] = [
  { name: "quiet", workVisibility: "quiet", reasoningMode: "collapsed", toolCallsMode: "collapsed" },
  { name: "balanced", workVisibility: "balanced", reasoningMode: "balanced", toolCallsMode: "balanced" },
  { name: "verbose", workVisibility: "verbose", reasoningMode: "expanded", toolCallsMode: "expanded" },
  { name: "thinking open", workVisibility: "balanced", reasoningMode: "expanded", toolCallsMode: "balanced" },
  { name: "thinking collapsed", workVisibility: "verbose", reasoningMode: "collapsed", toolCallsMode: "expanded" },
  { name: "tool calls locked open", workVisibility: "balanced", reasoningMode: "locked_open", toolCallsMode: "locked_open" },
  { name: "reasoning off", workVisibility: "balanced", reasoningMode: "off", toolCallsMode: "balanced" },
  { name: "tool calls off", workVisibility: "balanced", reasoningMode: "balanced", toolCallsMode: "off" },
  { name: "all off", workVisibility: "quiet", reasoningMode: "off", toolCallsMode: "off" },
];

async function mount(view: View, privateMode: boolean) {
  function Harness() {
    const runtime = useLocalRuntime(adapter, {
      initialMessages: privateMode ? PRIVATE : NORMAL,
    });
    return (
      <AssistantRuntimeProvider runtime={runtime}>
        <DigichatThread
          welcome="hi"
          placeholder="Ask"
          privateMode={privateMode}
          workVisibility={view.workVisibility}
          reasoningMode={view.reasoningMode}
          toolCallsMode={view.toolCallsMode}
        />
      </AssistantRuntimeProvider>
    );
  }
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness />);
  });
  await act(async () => {});
  return { host, unmount: () => act(() => root.unmount()) };
}

const SLOTS = [
  "aui_work-chain-trigger",
  "tool-group-root",
  "tool-group-trigger-label",
  "reasoning-trigger-label",
  "tool-fallback-trigger-label",
];

/** What the reader sees of the work: the chain header, the group, each row's label and glyph. */
function signature(host: HTMLElement): string[] {
  const out: string[] = [];
  const selector = SLOTS.map((slot) => `[data-slot="${slot}"]`).join(",");
  for (const el of host.querySelectorAll<HTMLElement>(selector)) {
    const slot = el.getAttribute("data-slot");
    if (slot === "aui_work-chain-trigger") {
      out.push(`chain expanded=${el.getAttribute("aria-expanded")} "${el.textContent?.trim()}"`);
    } else if (slot === "tool-group-root") {
      out.push(`group ${el.hasAttribute("data-open") ? "open" : "closed"}`);
    } else {
      const row = el.parentElement?.closest('[data-slot="reasoning-trigger"],[data-slot="tool-fallback-trigger"]') ?? el.parentElement;
      const glyph = row?.querySelector('[data-slot="dot-matrix"]')?.getAttribute("data-state");
      out.push(`${slot} "${el.textContent?.trim()}" glyph=${glyph}`);
    }
  }
  return out;
}

async function click(el: Element | null | undefined) {
  if (!el) return;
  await act(async () => {
    (el as HTMLElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await act(async () => {});
}

async function openHeader(host: HTMLElement) {
  const trig = host.querySelector('[data-slot="aui_work-chain-trigger"]');
  if (trig && trig.getAttribute("aria-expanded") !== "true") await click(trig);
}

async function openGroup(host: HTMLElement) {
  const group = host.querySelector('[data-slot="tool-group-root"]');
  if (group && !group.hasAttribute("data-open")) {
    await click(group.querySelector('[data-slot="tool-group-trigger"]'));
  }
}

const BODIES =
  '[data-slot="tool-fallback-content"],[data-slot="tool-fallback-args"],[data-slot="tool-fallback-result"],[data-slot="reasoning-content"],[data-slot="reasoning-text"]';

afterEach(() => {
  document.body.replaceChildren();
});

describe("private mode renders the work like normal mode", () => {
  for (const view of VIEWS) {
    it(`matches normal at rest, header open and group open (${view.name})`, async () => {
      const normal = await mount(view, false);
      const priv = await mount(view, true);

      expect(signature(priv.host)).toEqual(signature(normal.host));

      await openHeader(normal.host);
      await openHeader(priv.host);
      expect(signature(priv.host)).toEqual(signature(normal.host));

      await openGroup(normal.host);
      await openGroup(priv.host);
      expect(signature(priv.host)).toEqual(signature(normal.host));

      // Nothing private ever mounts a body, and nothing of a payload reaches it.
      expect(priv.host.querySelector(BODIES)).toBeNull();
      expect(priv.host.textContent).not.toContain(MARK);
      priv.unmount();
      normal.unmount();
    });
  }

  it("uses the normal labels: Reasoning, not Thought", async () => {
    const priv = await mount(VIEWS[2]!, true);
    await openHeader(priv.host);
    await openGroup(priv.host);
    const text = priv.host.textContent ?? "";
    expect(text).toContain("Reasoning");
    expect(text).not.toContain("Thought");
    expect(text).toContain("Used tool");
    expect(text).toContain("2 tool calls");
    priv.unmount();
  });
});

describe("private rows do not open", () => {
  for (const view of VIEWS.slice(0, 3)) {
    it(`clicking a private reasoning or tool row opens nothing (${view.name})`, async () => {
      const priv = await mount(view, true);
      await openHeader(priv.host);
      await openGroup(priv.host);
      const rows = [
        ...priv.host.querySelectorAll('[data-slot="tool-fallback-trigger"],[data-slot="reasoning-trigger"]'),
      ];
      expect(rows.length).toBe(3);
      for (const row of rows) {
        // Not a control: no button, no expanded state, no chevron, no hover or press style.
        expect(row.tagName).not.toBe("BUTTON");
        expect(row.closest("button")).toBeNull();
        expect(row.hasAttribute("aria-expanded")).toBe(false);
        expect(row.querySelector(".aui-disclosure-chevron")).toBeNull();
        expect(row.className).not.toMatch(/hover:|active:/);
        expect(row.className).toContain("pointer-events-none");
        await click(row);
        await click(row.querySelector('[data-slot$="-label"]'));
      }
      expect(priv.host.querySelector(BODIES)).toBeNull();
      expect(priv.host.querySelectorAll('[data-slot="tool-fallback-trigger"]').length).toBe(2);
      priv.unmount();
    });
  }

  it("still opens a normal tool row on click", async () => {
    const normal = await mount(VIEWS[2]!, false);
    await openHeader(normal.host);
    await openGroup(normal.host);
    const row = normal.host.querySelector('[data-slot="tool-fallback-trigger"]');
    expect(row?.tagName).toBe("BUTTON");
    expect(normal.host.querySelector('[data-slot="tool-fallback-content"]')).toBeNull();
    await click(row);
    expect(normal.host.querySelector('[data-slot="tool-fallback-content"]')).not.toBeNull();
    expect(normal.host.textContent).toContain(`${MARK}-args`);
    normal.unmount();
  });
});
