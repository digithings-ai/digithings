// @vitest-environment happy-dom
import {
  AssistantRuntimeProvider,
  type ChatModelAdapter,
  unstable_useSlashCommandAdapter,
  useLocalRuntime,
} from "@assistant-ui/react";
import { act, useMemo } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DigichatThread } from "../DigichatThread";

// The picker's back key used to dispatch a synthetic Escape on `document`.
// That event's target is `document`, so it never descends into the composer
// and the composer's own keydown handler never saw it: the picker stayed
// open. The back key now closes the picker through the picker's own scope,
// the same path upstream's Escape handler uses.
//
// These tests therefore drive the real control with a real key press on the
// focused composer textarea. They fail against the pre-fix source.
const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

function Harness() {
  const runtime = useLocalRuntime(adapter);
  const slash = unstable_useSlashCommandAdapter({
    commands: [{ id: "clear", label: "Clear", execute: vi.fn() }],
  });
  const slashTrigger = useMemo(
    () => ({ adapter: slash.adapter, action: slash.action }),
    [slash],
  );
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <DigichatThread
        welcome="inspect this"
        placeholder="Ask digithings…"
        onComposerSubmit={vi.fn()}
        slash={slashTrigger}
      />
    </AssistantRuntimeProvider>
  );
}

async function mount() {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness />);
  });
  return {
    host,
    unmount: () => act(() => root.unmount()),
  };
}

async function typeInto(host: HTMLElement, text: string) {
  const input = host.querySelector<HTMLTextAreaElement>("textarea");
  if (!input) throw new Error("composer textarea not found");
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(input, text);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  return input;
}

function picker(host: HTMLElement) {
  return host.querySelector('[data-slot="composer-trigger-popover"]');
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("gallery composer trigger popover", () => {
  it("closes the picker when the back key is pressed", async () => {
    const { host, unmount } = await mount();
    const input = await typeInto(host, "/");

    expect(picker(host)).toBeTruthy();

    await act(async () => {
      input.dispatchEvent(
        new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }),
      );
    });

    expect(picker(host)).toBeNull();

    unmount();
  });
});
