// @vitest-environment happy-dom
import type { ChatModelAdapter, ThreadAssistantMessagePart } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useAui, useLocalRuntime } from "@assistant-ui/react";
import { act, useEffect, type FC } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { setDigichatWarmupPhase } from "./boot-signal";
import { DigichatThread } from "./DigichatThread";

/**
 * The pre-response loader and the Working / Worked header render the same
 * lead: one marker slot, one label slot, one row class.
 */

type Part = ThreadAssistantMessagePart;
const conn = (data: Record<string, unknown>) =>
  ({ type: "data", name: "connection", data }) as unknown as Part;

function controlledAdapter() {
  let push: ((parts: Part[]) => void) | null = null;
  const queue: Part[][] = [];
  const adapter: ChatModelAdapter = {
    async *run({ abortSignal }) {
      while (!abortSignal.aborted) {
        const next =
          queue.shift() ??
          (await new Promise<Part[]>((resolve) => {
            push = resolve;
            abortSignal.addEventListener("abort", () => resolve([]));
          }));
        push = null;
        if (abortSignal.aborted) return;
        yield { content: next };
      }
    },
  };
  const step = async (parts: Part[]) => {
    await act(async () => {
      if (push) push(parts);
      else queue.push(parts);
      await new Promise((r) => setTimeout(r, 20));
    });
  };
  return { adapter, step };
}

const Send: FC = () => {
  const aui = useAui();
  useEffect(() => {
    aui.thread().append("hello");
  }, [aui]);
  return null;
};

async function mount(adapter: ChatModelAdapter) {
  const Harness: FC = () => {
    const runtime = useLocalRuntime(adapter);
    return (
      <AssistantRuntimeProvider runtime={runtime}>
        <DigichatThread placeholder="Ask digichat…" />
        <Send />
      </AssistantRuntimeProvider>
    );
  };
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness />);
    await new Promise((r) => setTimeout(r, 20));
  });
  return { host, unmount: () => act(() => root.unmount()) };
}

function lead(row: Element | null) {
  expect(row).toBeTruthy();
  expect(row!.classList.contains("aui-work-status")).toBe(true);
  const marker = row!.querySelector('[data-slot="aui_work-status-marker"] [data-slot="dot-matrix"]');
  expect(marker).toBeTruthy();
  expect(marker!.className).toContain("!size-3");
  return row!.querySelector('[data-slot="aui_work-status-label"]');
}

afterEach(() => {
  document.body.replaceChildren();
  setDigichatWarmupPhase("idle");
});

describe("loader and work header share one lead", () => {
  it("keeps the marker and the label slot from the loader through Worked", async () => {
    const { adapter, step } = controlledAdapter();
    const { host, unmount } = await mount(adapter);

    await step([conn({ state: "connecting" })]);
    const indicator = host.querySelector('[data-slot="aui_assistant-message-indicator"]');
    lead(indicator);
    expect(host.querySelector('[data-slot="aui_work-chain-trigger"]')).toBeNull();

    await act(async () => setDigichatWarmupPhase("waking"));
    await step([conn({ state: "connecting", message: "Waking up services…" })]);
    expect(lead(host.querySelector('[data-slot="aui_assistant-message-indicator"]'))?.textContent).toBe(
      "Waking up services…",
    );

    const work = [
      conn({ state: "connected" }),
      { type: "reasoning", text: "Looking it up." } as Part,
      {
        type: "tool-call",
        toolCallId: "t1",
        toolName: "digisearch",
        argsText: "{}",
        result: "ok",
      } as Part,
      {
        type: "tool-call",
        toolCallId: "t2",
        toolName: "digivault_search_notes",
        argsText: "{}",
        result: "ok",
      } as Part,
    ];
    await step(work);
    expect(host.querySelector('[data-slot="aui_assistant-message-indicator"]')).toBeNull();
    const header = host.querySelector('[data-slot="aui_work-chain-trigger"]');
    const working = lead(header);
    expect(working?.textContent).toMatch(/Working/);
    expect(header?.querySelector('[data-slot="disclosure-chevron"]')).toBeTruthy();

    await step([...work, { type: "text", text: "Done." } as Part]);
    const rested = lead(host.querySelector('[data-slot="aui_work-chain-trigger"]'));
    expect(rested?.textContent).toMatch(/Worked|Used|Thought/);

    unmount();
  });
});
