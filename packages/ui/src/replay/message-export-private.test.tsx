/**
 * @vitest-environment happy-dom
 *
 * Private mode hides the per-message export on every skin, not only
 * digichat: ThreadSkinView hands the host's flag to the shared menu, and the
 * export runners refuse on their own while a private chat is mounted.
 */
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ThreadSkinView } from "../components/chat/skins/thread-skin-view";
import type { ThreadSkin } from "../components/chat/skins/thread-skins";
import {
  ChatPrivateModeProvider,
  isChatPrivateMode,
} from "../components/chat/stock/chat-private-mode";
import { exportConversation, exportMessage } from "./chat-export-run";

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
  { role: "user", content: [{ type: "text", text: "secret-question-token" }] },
  { role: "assistant", content: [{ type: "text", text: "plain-answer-token" }] },
];

function Harness({ skin, privateMode }: { skin: ThreadSkin; privateMode: boolean }) {
  const runtime = useLocalRuntime(adapter, { initialMessages: MESSAGES });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadSkinView skin={skin} digichat={{ privateMode }} />
    </AssistantRuntimeProvider>
  );
}

let root: Root | null = null;

async function mount(skin: ThreadSkin, privateMode: boolean): Promise<Element> {
  const host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(<Harness skin={skin} privateMode={privateMode} />);
  });
  return vi.waitFor(
    () => {
      const answer = [...document.querySelectorAll("[data-role='assistant']")].find((el) =>
        el.textContent?.includes("plain-answer-token"),
      );
      expect(answer).toBeTruthy();
      return answer!;
    },
    { timeout: 5000 },
  );
}

function moreButtons(message: Element): HTMLButtonElement[] {
  return [...message.querySelectorAll("button")].filter(
    (button) =>
      button.getAttribute("aria-label") === "More" || button.textContent?.includes("More"),
  );
}

afterEach(async () => {
  if (root) await act(async () => root!.unmount());
  root = null;
  saved.length = 0;
  document.body.replaceChildren();
});

describe.each(["chatgpt", "base"] as const)("%s skin in a private session", (skin) => {
  it("renders the message More menu when the session is not private", async () => {
    const answer = await mount(skin, false);
    await act(async () => {
      answer.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    expect(moreButtons(answer).length).toBeGreaterThan(0);
    expect(isChatPrivateMode()).toBe(false);
  });

  it("renders no message export menu, and the runner refuses", async () => {
    const answer = await mount(skin, true);
    await act(async () => {
      answer.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
    });
    expect(moreButtons(answer)).toHaveLength(0);
    expect(document.querySelector("[data-slot='message-export-trigger']")).toBeNull();
    expect(isChatPrivateMode()).toBe(true);

    await exportMessage({
      format: "md",
      message: MESSAGES[1],
      messageId: "a1",
      messages: MESSAGES,
      trigger: null,
      doc: document,
    });
    await exportConversation({ format: "md", messages: MESSAGES, doc: document });
    expect(saved).toHaveLength(0);
  });
});

describe("export runners and the shared private flag", () => {
  it("refuse while a private provider is mounted and run again once it is gone", async () => {
    const host = document.createElement("div");
    document.body.append(host);
    root = createRoot(host);
    await act(async () => {
      root!.render(
        <ChatPrivateModeProvider privateMode>
          <span />
        </ChatPrivateModeProvider>,
      );
    });
    const message = { id: "a1", role: "assistant", content: [{ type: "text", text: "A" }] };
    await exportMessage({ format: "md", message, messageId: "a1", trigger: null, doc: document });
    await exportMessage({ format: "html", message, messageId: "a1", trigger: null, doc: document });
    await exportConversation({ format: "md", messages: [message], doc: document });
    expect(saved).toHaveLength(0);

    await act(async () => {
      root!.render(
        <ChatPrivateModeProvider privateMode={false}>
          <span />
        </ChatPrivateModeProvider>,
      );
    });
    expect(isChatPrivateMode()).toBe(false);
    await exportMessage({ format: "md", message, messageId: "a1", trigger: null, doc: document });
    expect(saved.map((s) => s.body)).toEqual(["A"]);
  });

  it("refuses when the caller says the session is private", async () => {
    const message = { id: "a1", role: "assistant", content: [{ type: "text", text: "A" }] };
    await exportMessage({
      format: "md",
      message,
      messageId: "a1",
      trigger: null,
      doc: document,
      privateMode: true,
    });
    await exportConversation({
      format: "md",
      messages: [message],
      doc: document,
      privateMode: true,
    });
    expect(saved).toHaveLength(0);
  });
});
