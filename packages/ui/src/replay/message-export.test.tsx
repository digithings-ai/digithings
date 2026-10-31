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

vi.mock("../components/chat/transcript/save-file", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../components/chat/transcript/save-file")>()),
  saveTextFile: (name: string, body: string) => {
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

/** More → Export ▸ → the format row. Both menus are portaled to the body. */
async function pickFormat(
  user: ReturnType<typeof userEvent.setup>,
  more: HTMLElement,
  format: "md" | "html",
): Promise<HTMLElement> {
  await user.click(more);
  const sub = await vi.waitFor(() => {
    const el = document.body.querySelector<HTMLElement>("[data-slot='message-export-trigger']");
    expect(el).toBeTruthy();
    return el!;
  });
  expect(sub.textContent).toContain("Export");
  await user.click(sub);
  return vi.waitFor(() => {
    const el = document.body.querySelector<HTMLElement>(`[data-export-format='${format}']`);
    expect(el).toBeTruthy();
    return el!;
  });
}

describe("message menu Export submenu", () => {
  it("clicks the portaled HTML row and saves only that answer", async () => {
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
    const betaId = beta!.getAttribute("data-message-id") ?? "";
    expect(betaId).not.toBe("");
    const decoyHost = document.createElement("div");
    decoyHost.hidden = true;
    const decoyThread = document.createElement("div");
    decoyThread.className = "aui-thread-root";
    const decoyMessage = document.createElement("div");
    decoyMessage.setAttribute("data-role", "assistant");
    decoyMessage.setAttribute("data-message-id", betaId);
    const decoyBody = document.createElement("div");
    decoyBody.className = "aui-assistant-message-content";
    decoyBody.textContent = "embed-duplicate-token";
    decoyMessage.append(decoyBody);
    decoyThread.append(decoyMessage);
    decoyHost.append(decoyThread);
    document.body.prepend(decoyHost);
    const more = [...beta!.querySelectorAll("button")].find((button) =>
      button.textContent?.includes("More"),
    );
    expect(more).toBeTruthy();

    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const item = await pickFormat(user, more!, "html");
    expect(item.textContent).toContain("HTML (.html)");
    expect(thread!.contains(item!)).toBe(false);
    expect(item!.closest(".aui-thread-root")).toBeNull();

    await act(async () => item!.click());
    await act(async () => {
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => resolve());
      });
    });
    await vi.waitFor(() => expect(saved).toHaveLength(1));

    const body = saved[0]!.body;
    expect(saved[0]!.name).toMatch(/beta-question-token\.html$/);
    expect(body).not.toContain("beta-question-token");
    expect(body).toContain("beta-answer-token");
    expect(body).not.toContain("alpha-question-token");
    expect(body).not.toContain("alpha-answer-token");
    expect(body).not.toContain("embed-duplicate-token");
    expect(body).not.toContain("data-scroll-locked");
    expect(body).not.toContain("data-aria-hidden");
    expect(document.body.textContent).toContain("alpha-question-token");

    await act(async () => root.unmount());
    vi.unstubAllGlobals();
  });

  it("exports an older answer after its action bar unmounts", async () => {
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

    const alpha = [...document.querySelectorAll("[data-role='assistant']")].find((el) =>
      el.textContent?.includes("alpha-answer-token"),
    );
    expect(alpha).toBeTruthy();
    await act(async () => {
      alpha!.dispatchEvent(new MouseEvent("mouseenter", { bubbles: false }));
    });
    const more = await vi.waitFor(() => {
      const button = [...alpha!.querySelectorAll("button")].find((el) =>
        el.textContent?.includes("More"),
      );
      expect(button).toBeTruthy();
      return button!;
    });
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const item = await pickFormat(user, more, "html");
    await act(async () => {
      alpha!.dispatchEvent(new MouseEvent("mouseleave", { bubbles: false }));
    });
    await act(async () => item.click());
    await act(async () => {
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => resolve());
      });
    });
    await vi.waitFor(() => expect(saved).toHaveLength(1));

    const body = saved[0]!.body;
    expect(body).not.toContain("alpha-question-token");
    expect(body).toContain("alpha-answer-token");
    expect(body).not.toContain("beta-question-token");
    expect(body).not.toContain("beta-answer-token");
    const stillThere = [...alpha!.querySelectorAll("button")].some((button) =>
      button.textContent?.includes("More"),
    );
    expect(stillThere).toBe(false);

    await act(async () => root.unmount());
    vi.unstubAllGlobals();
  });

  it("saves that answer as markdown, without the question", async () => {
    const host = document.createElement("div");
    document.body.append(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(<Harness />);
    });
    const beta = [...document.querySelectorAll("[data-role='assistant']")].find((el) =>
      el.textContent?.includes("beta-answer-token"),
    );
    const more = [...beta!.querySelectorAll("button")].find((button) =>
      button.textContent?.includes("More"),
    );
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const item = await pickFormat(user, more!, "md");
    expect(item.textContent).toContain("Markdown (.md)");
    await act(async () => item.click());
    await act(async () => {
      await new Promise<void>((resolve) => {
        requestAnimationFrame(() => resolve());
      });
    });
    await vi.waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0]!.name).toMatch(/beta-question-token\.md$/);
    expect(saved[0]!.body).toBe("beta-answer-token");
    await act(async () => root.unmount());
  });
});
