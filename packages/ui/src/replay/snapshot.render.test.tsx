/**
 * @vitest-environment happy-dom
 */
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { DigichatThread } from "../components/chat/DigichatThread";
import { setExportKeepMounted } from "./export-mount";
import { serializeSnapshot, transformSnapshotDom } from "./snapshot";

const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

const MESSAGES: ThreadMessageLike[] = [
  {
    role: "user",
    content: [{ type: "text", text: "What is the overnight book?" }],
  },
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "t1",
        toolName: "digisearch",
        argsText: '{"q":"book"}',
        result: "vault-row-marker",
      },
      { type: "text", text: "The book is flat." },
    ],
  },
];

function Harness() {
  const runtime = useLocalRuntime(adapter, { initialMessages: MESSAGES });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <DigichatThread welcome="inspect this" placeholder="Ask digichat…" />
    </AssistantRuntimeProvider>
  );
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("rendered thread snapshot", () => {
  it("exports the closed tool call as a details element with its result", async () => {
    const host = document.createElement("div");
    host.setAttribute("data-deployment", "northwind");
    document.body.append(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<Harness />);
    });

    setExportKeepMounted(true);
    const live = document.documentElement.cloneNode(true) as HTMLElement;
    setExportKeepMounted(false);
    transformSnapshotDom(live);
    const html = serializeSnapshot(live, ".aui-md { white-space: pre-wrap; }");

    expect(html.toLowerCase()).not.toContain("<script");
    expect(html).not.toContain("<textarea");
    expect(html).not.toContain("aui-composer");
    expect(html).toContain("What is the overnight book?");
    expect(html).toContain("The book is flat.");
    expect(html).toContain("vault-row-marker");
    expect(html).not.toMatch(/url\(\s*['"]?https?:/i);
    expect(html).not.toMatch(/<img[^>]+src=["']https?:/i);
    const tool = live.querySelector("[data-slot='tool-fallback-root']");
    expect(tool?.tagName).toBe("DETAILS");
    expect(tool?.querySelector("summary")).toBeTruthy();

    await act(async () => root.unmount());
  });
});
