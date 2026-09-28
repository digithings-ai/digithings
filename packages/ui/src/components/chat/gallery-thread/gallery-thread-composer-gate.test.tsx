// @vitest-environment happy-dom
import {
  AssistantRuntimeProvider,
  type ChatModelAdapter,
  useLocalRuntime,
} from "@assistant-ui/react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DigichatThread } from "../DigichatThread";

// The gallery composer must let a consumer see every send through the form's
// `onSubmit`. The digichat embed's free-turn gate is mounted there (#4456): it
// counts a free question and, at the threshold, holds the turn. Pressing Enter
// reached it, because `ComposerPrimitive.Input` submits the form. The Send
// control did not — it was `ComposerPrimitive.Send`, which assistant-ui renders
// as `type="button"` wired to `onClick -> send()`, so `onSubmit` never ran and
// the `0/3` counter never advanced for button sends.
//
// These tests therefore drive the real control with a real click. They fail
// against the pre-fix source.
const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

function Harness({
  onComposerSubmit,
}: {
  onComposerSubmit: (event: { preventDefault: () => void }) => void;
}) {
  const runtime = useLocalRuntime(adapter);
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <DigichatThread
        welcome="inspect this"
        placeholder="Ask digichat…"
        onComposerSubmit={onComposerSubmit}
      />
    </AssistantRuntimeProvider>
  );
}

async function mount(
  onComposerSubmit: (event: { preventDefault: () => void }) => void,
) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness onComposerSubmit={onComposerSubmit} />);
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
}

function sendControl(host: HTMLElement) {
  const send = host.querySelector<HTMLButtonElement>(".aui-composer-send");
  if (!send) throw new Error("send control not found");
  return send;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("gallery composer send control", () => {
  it("pins the send controls right when no attachment adapter is mounted", async () => {
    // This harness runs adapter-less, so AddAttachment renders null — the
    // reported product-mode state. justify-between alone would collapse the
    // lone send controls left; ml-auto keeps them right regardless.
    const { host, unmount } = await mount(vi.fn());
    const controls = host.querySelector(".aui-composer-send-controls");
    expect(controls?.className).toMatch(/(?:^|\s)ml-auto(?:\s|$)/);
    unmount();
  });

  it("is a real form submit and stays visible but disabled when empty", async () => {
    const { host, unmount } = await mount(vi.fn());

    // An empty composer still shows the control (a disabled affordance), as it
    // did before the fix — `ComposerPrimitive.Send` rendered a disabled button.
    const empty = sendControl(host);
    expect(empty.getAttribute("type")).toBe("submit");
    expect(empty.closest("form")).toBeTruthy();
    expect(empty.disabled).toBe(true);

    await typeInto(host, "hello");
    expect(sendControl(host).disabled).toBe(false);

    unmount();
  });

  it("delivers a Send click to the form's onSubmit exactly once", async () => {
    // One click, one gate run. A `type="submit"` button also submits its form
    // on activation, so a click handler that additionally calls
    // `requestSubmit()` would fire `submit` twice — and the gate with it.
    const onComposerSubmit = vi.fn((event: { preventDefault: () => void }) => {
      event.preventDefault();
    });
    const { host, unmount } = await mount(onComposerSubmit);
    await typeInto(host, "hello");

    await act(async () => {
      sendControl(host).click();
    });

    expect(onComposerSubmit).toHaveBeenCalledTimes(1);
    // The gate held the send, so no user message reached the thread.
    expect(host.querySelectorAll('[data-slot="aui_user-message-root"]').length).toBe(0);

    unmount();
  });

  it("sends exactly one message when the gate allows the turn", async () => {
    const onComposerSubmit = vi.fn();
    const { host, unmount } = await mount(onComposerSubmit);
    await typeInto(host, "hello");

    await act(async () => {
      sendControl(host).click();
    });
    await act(async () => {});

    expect(onComposerSubmit).toHaveBeenCalledTimes(1);
    expect(host.querySelectorAll('[data-slot="aui_user-message-root"]').length).toBe(1);

    unmount();
  });

  it("reaches onSubmit from the Enter key too", async () => {
    // The pre-existing path, pinned so the two entry points stay equivalent.
    const onComposerSubmit = vi.fn((event: { preventDefault: () => void }) => {
      event.preventDefault();
    });
    const { host, unmount } = await mount(onComposerSubmit);
    await typeInto(host, "hello");

    const input = host.querySelector("textarea");
    await act(async () => {
      input?.closest("form")?.requestSubmit();
    });

    expect(onComposerSubmit).toHaveBeenCalledTimes(1);

    unmount();
  });
});
