// @vitest-environment happy-dom
import {
  AssistantRuntimeProvider,
  type ChatModelAdapter,
  useLocalRuntime,
} from "@assistant-ui/react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { DigichatThread } from "../DigichatThread";
import { SKIN_CREDIT_TEXT } from "../stock/skin-credit";

// The gallery Thread's default Footer renders the "powered by digichat"
// branding in normal flow below the composer in every state. The footer's
// sticky bottom-0 mt-auto docks it to the page bottom unconditionally, so
// no absolute overlay is needed — one painted over the composer, with the
// textbox cutting the credit off.
const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

function Harness() {
  const runtime = useLocalRuntime(adapter);
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <DigichatThread welcome="inspect this" placeholder="Ask digichat…" />
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

async function sendFirstMessage(host: HTMLElement) {
  const input = host.querySelector<HTMLTextAreaElement>("textarea");
  if (!input) throw new Error("composer textarea not found");
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(input, "hello");
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const send = host.querySelector<HTMLButtonElement>(".aui-composer-send");
  if (!send) throw new Error("send control not found");
  await act(async () => {
    send.click();
  });
  await act(async () => {});
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("gallery Thread branding footer", () => {
  it("renders the credit in-flow inside the docked footer on an empty thread", async () => {
    const { host, unmount } = await mount();
    const credit = host.querySelector('[data-testid="skin-credit"]');
    expect(credit?.textContent).toBe(SKIN_CREDIT_TEXT);
    // In-flow inside the bottom-docked footer — never an overlay on the composer.
    expect(credit?.closest(".aui-thread-viewport-footer")).not.toBeNull();
    unmount();
  });

  it("shows the credit below the composer once the first message is sent", async () => {
    const { host, unmount } = await mount();
    await sendFirstMessage(host);

    expect(
      host.querySelectorAll('[data-slot="aui_user-message-root"]').length,
    ).toBe(1);
    const credit = host.querySelector('[data-testid="skin-credit"]');
    expect(credit?.textContent).toBe(SKIN_CREDIT_TEXT);

    unmount();
  });
});
