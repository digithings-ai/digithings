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

function rect(top: number, bottom: number): DOMRect {
  return { top, bottom } as DOMRect;
}

// happy-dom has no layout engine, so the two nodes the gate measures are given
// synthetic geometry and a scroll event is dispatched to re-run the gate.
async function setLayout(
  host: HTMLElement,
  groupBottom: number,
  composerTop: number,
) {
  const group = host.querySelector<HTMLElement>(
    '[data-slot="aui_message-group"]',
  );
  const composer = host.querySelector<HTMLElement>(
    '[data-slot="aui_composer-shell"]',
  );
  const viewport = host.querySelector<HTMLElement>(
    '[data-slot="aui_thread-viewport"]',
  );
  if (!group || !composer || !viewport) {
    throw new Error("thread layout nodes not found");
  }
  group.getBoundingClientRect = () => rect(0, groupBottom);
  composer.getBoundingClientRect = () => rect(composerTop, composerTop + 60);
  await act(async () => {
    viewport.dispatchEvent(new Event("scroll"));
  });
}

function button(host: HTMLElement) {
  return host.querySelector(".aui-thread-scroll-to-bottom");
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("gallery-thread scroll-to-bottom visibility", () => {
  it("stays hidden while every message sits above the composer", async () => {
    const { host, unmount } = await mount();
    await setLayout(host, 400, 500);
    expect(button(host)).toBeNull();
    unmount();
  });

  it("appears once a message is hidden under the composer, then hides again", async () => {
    const { host, unmount } = await mount();

    await setLayout(host, 620, 500);
    expect(button(host)).not.toBeNull();

    await setLayout(host, 400, 500);
    expect(button(host)).toBeNull();

    unmount();
  });
});
