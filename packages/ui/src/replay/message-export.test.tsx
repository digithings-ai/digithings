/**
 * @vitest-environment happy-dom
 *
 * The menu item is portaled to document.body. The export must still save
 * only that question and answer.
 */
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DigichatThread } from "../components/chat/DigichatThread";

const saved = vi.hoisted(() => [] as Array<{ name: string; body: string }>);

vi.mock("../components/chat/transcript", () => ({
  downloadTextFile: (name: string, body: string) => {
    saved.push({ name, body });
  },
}));

const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

const MESSAGES: ThreadMessageLike[] = [
  { role: "user", content: [{ type: "text", text: "alpha-question-token" }] },
  { role: "assistant", content: [{ type: "text", text: "alpha-answer-token" }] },
  { role: "user", content: [{ type: "text", text: "beta-question-token" }] },
  { role: "assistant", content: [{ type: "text", text: "beta-answer-token" }] },
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
  saved.length = 0;
  document.body.replaceChildren();
});

describe("message menu Export as HTML", () => {
  it("clicks the portaled menu item and saves only that question and answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 404 })),
    );
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<Harness />);
    });

    expect(document.body.textContent).toContain("alpha-question-token");
    expect(document.body.textContent).toContain("beta-answer-token");
    const thread = document.querySelector(".aui-thread-root");
    expect(thread).not.toBeNull();
    const beta = [...document.querySelectorAll("[data-role='assistant']")].find((el) =>
      el.textContent?.includes("beta-answer-token"),
    );
    expect(beta).toBeTruthy();
    const more = [...beta!.querySelectorAll("button")].find((button) =>
      button.textContent?.includes("More"),
    );
    expect(more).toBeTruthy();

    const user = userEvent.setup();
    await user.click(more!);
    const item = [...document.body.querySelectorAll("[role='menuitem']")].find((el) =>
      el.textContent?.includes("Export as HTML"),
    );
    expect(item).toBeTruthy();
    expect(thread!.contains(item!)).toBe(false);
    expect(item!.closest(".aui-thread-root")).toBeNull();

    await user.click(item!);
    await vi.waitFor(() => expect(saved).toHaveLength(1));

    const body = saved[0]!.body;
    expect(body).toContain("beta-question-token");
    expect(body).toContain("beta-answer-token");
    expect(body).not.toContain("alpha-question-token");
    expect(body).not.toContain("alpha-answer-token");
    expect(document.body.textContent).toContain("alpha-question-token");

    await act(async () => root.unmount());
    vi.unstubAllGlobals();
  });
});
