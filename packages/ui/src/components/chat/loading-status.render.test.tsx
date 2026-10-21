// @vitest-environment happy-dom
import type { ChatModelAdapter, ThreadAssistantMessagePart } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useAui, useLocalRuntime } from "@assistant-ui/react";
import { act, useEffect, type FC } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { setDigichatWarmupPhase } from "./boot-signal";
import { DigichatThread } from "./DigichatThread";
import { BaseThread } from "./skins/base/thread";

/**
 * DIG-4459: the pre-response loading row is the animation alone unless the
 * server sent a status message, and the "Working" block only appears once
 * the agent produced output. Mock stream only — nothing leaves the test.
 */

type Part = ThreadAssistantMessagePart;
const conn = (data: Record<string, unknown>) =>
  ({ type: "data", name: "connection", data }) as unknown as Part;

/** A stream that yields each step on demand and never ends on its own. */
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

async function mount(Skin: FC, adapter: ChatModelAdapter) {
  const Harness: FC = () => {
    const runtime = useLocalRuntime(adapter);
    return (
      <AssistantRuntimeProvider runtime={runtime}>
        <Skin />
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

const indicator = (host: HTMLElement) =>
  host.querySelector<HTMLElement>('[data-slot="aui_assistant-message-indicator"]');
/** The visible text of the row, without the screen-reader-only label. */
const visibleText = (el: HTMLElement | null) => {
  if (!el) return null;
  const clone = el.cloneNode(true) as HTMLElement;
  clone.querySelectorAll(".sr-only, [data-slot='screen-reader-name']").forEach((n) => n.remove());
  return (clone.textContent ?? "").trim();
};
const workChain = (host: HTMLElement) =>
  host.querySelector('[data-slot="aui_work-chain-trigger"]');

const Gallery: FC = () => <DigichatThread placeholder="Ask digichat…" />;

afterEach(() => {
  document.body.replaceChildren();
  setDigichatWarmupPhase("idle");
});

describe.each([
  ["gallery skin", Gallery],
  ["base skin", BaseThread as FC],
])("pre-response loading row (%s)", (_name, Skin) => {
  it("shows the animation alone while we only wait for a response", async () => {
    const { adapter, step } = controlledAdapter();
    const { host, unmount } = await mount(Skin, adapter);
    await step([conn({ state: "connecting" })]);
    const row = indicator(host);
    expect(row).toBeTruthy();
    expect(row?.querySelector('[data-slot="dot-matrix"], svg, [role="img"]')).toBeTruthy();
    expect(visibleText(row)).toBe("");
    expect(host.textContent).not.toMatch(/Connecting|Warming up/);
    unmount();
  });

  it("shows the exact status message the server sent", async () => {
    const { adapter, step } = controlledAdapter();
    const { host, unmount } = await mount(Skin, adapter);
    await step([
      conn({ state: "connecting" }),
      conn({ state: "warming_up", message: "Waiting for model capacity — retrying in 8s" }),
    ]);
    expect(visibleText(indicator(host))).toBe("Waiting for model capacity — retrying in 8s");
    unmount();
  });

  it("shows the warm-up probe's status while services wake", async () => {
    const { adapter, step } = controlledAdapter();
    const { host, unmount } = await mount(Skin, adapter);
    await act(async () => setDigichatWarmupPhase("waking"));
    await step([conn({ state: "connecting" })]);
    expect(visibleText(indicator(host))).toBe("Waking up services…");
    unmount();
  });
});

describe("work block only after output (gallery skin)", () => {
  it("no Working block before output; it replaces the loading row once reasoning arrives", async () => {
    const { adapter, step } = controlledAdapter();
    const { host, unmount } = await mount(Gallery, adapter);
    await step([conn({ state: "connecting" })]);
    expect(workChain(host)).toBeNull();
    expect(indicator(host)).toBeTruthy();

    await step([
      conn({ state: "connected" }),
      { type: "reasoning", text: "Looking at the report…" } as Part,
    ]);
    expect(workChain(host)).toBeTruthy();
    expect(indicator(host)).toBeNull();
    unmount();
  });
});
