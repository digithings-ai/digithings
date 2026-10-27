// @vitest-environment happy-dom
import { AssistantRuntimeProvider, type ChatModelAdapter, useLocalRuntime } from "@assistant-ui/react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { DigichatThread } from "../DigichatThread";

const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

function Harness({ privateMode }: { privateMode?: boolean }) {
  const runtime = useLocalRuntime(adapter);
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <DigichatThread welcome="inspect this" placeholder="Ask digithings…" privateMode={privateMode} />
    </AssistantRuntimeProvider>
  );
}

async function mount(privateMode?: boolean) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness privateMode={privateMode} />);
  });
  return host;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("private chip", () => {
  it("shows a private chip above the composer only while private mode is on", async () => {
    const off = await mount(false);
    expect(off.querySelector("[data-slot='aui_private-mode-badge']")).toBeNull();

    document.body.replaceChildren();
    const on = await mount(true);
    const chip = on.querySelector("[data-slot='aui_private-mode-badge']");
    expect(chip?.textContent).toBe("private");
    expect(chip?.getAttribute("data-private")).toBe("on");
    expect(chip?.tagName).toBe("DIV");
  });
});
