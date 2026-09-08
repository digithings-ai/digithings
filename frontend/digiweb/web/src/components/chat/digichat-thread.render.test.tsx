// @vitest-environment happy-dom
import type { ChatModelAdapter } from "@assistant-ui/react";
import {
  AssistantRuntimeProvider,
  useLocalRuntime,
} from "@assistant-ui/react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { DigichatThread } from "./DigichatThread";

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

afterEach(() => {
  document.body.replaceChildren();
});

describe("DigichatThread", () => {
  it("left-aligns the terminal pane with a > composer glyph", async () => {
    const { host, unmount } = await mount();
    const thread = host.querySelector(".digichat-thread");
    expect(thread).toBeTruthy();
    expect(thread?.getAttribute("data-user-align")).toBe("left");
    expect(host.textContent).toContain("inspect this");
    expect(host.textContent).toContain(">");
    expect(host.querySelector('[aria-label="Message"]')).toBeTruthy();
    unmount();
  });
});
