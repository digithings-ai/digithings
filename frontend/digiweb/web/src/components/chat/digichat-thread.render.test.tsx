// @vitest-environment happy-dom
import type { ChatModelAdapter } from "@assistant-ui/react";
import {
  AssistantRuntimeProvider,
  AuiConfig,
  Suggestions,
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

const SUGGESTION_CONFIG = AuiConfig({
  suggestions: Suggestions(["run a backtest"]),
});

function Harness({
  body,
}: {
  body?: readonly string[];
}) {
  const runtime = useLocalRuntime(adapter);
  return (
    <AssistantRuntimeProvider runtime={runtime} config={SUGGESTION_CONFIG}>
      <DigichatThread
        welcome="inspect this"
        welcomeBody={body}
        placeholder="Ask digichat…"
      />
    </AssistantRuntimeProvider>
  );
}

async function mount(body?: readonly string[]) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness body={body} />);
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
  it("left-aligns the gallery Thread pane", async () => {
    const { host, unmount } = await mount();
    const thread = host.querySelector(".digichat-thread");
    expect(thread).toBeTruthy();
    expect(thread?.getAttribute("data-user-align")).toBe("left");
    expect(host.querySelector(".aui-root")).toBeTruthy();
    expect(host.textContent).toContain("inspect this");
    expect(host.querySelector('[aria-label="Message"]')).toBeTruthy();
    unmount();
  });

  it("docks welcome and example cubes in the footer above the composer", async () => {
    const { host, unmount } = await mount([
      "Scoped to the tools and data in this deployment.",
    ]);
    const footer = host.querySelector(".digichat-thread__footer");
    const welcome = footer?.querySelector('[data-slot="aui_thread-welcome"]');
    const composer = footer?.querySelector('[aria-label="Message"]');
    expect(welcome).toBeTruthy();
    expect(composer).toBeTruthy();
    expect(host.querySelector(".digichat-thread__viewport > [data-slot='aui_thread-welcome']")).toBeNull();
    expect(footer?.textContent).toContain("inspect this");
    expect(footer?.textContent).toContain("Scoped to the tools and data in this deployment.");
    expect(footer?.textContent).toContain("run a backtest");
    expect(host.querySelector(".aui-composer-input")).toBeTruthy();
    expect(host.querySelector('[data-slot="aui_composer-shell"]')).toBeTruthy();
    expect(host.querySelector('[data-state="example"]')).toBeTruthy();
    expect(host.textContent).not.toContain("// digichat");
    expect(host.querySelector(".digichat-chip")).toBeNull();
    const footerHtml = footer?.innerHTML ?? "";
    expect(footerHtml.indexOf("aui_thread-welcome")).toBeGreaterThanOrEqual(0);
    expect(footerHtml.indexOf("aui_thread-welcome")).toBeLessThan(
      footerHtml.indexOf('aria-label="Message"'),
    );
    unmount();
  });
});
