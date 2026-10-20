// @vitest-environment happy-dom
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DigichatThread } from "../DigichatThread";
import { isUnchangedEdit, shouldCommitEdit } from "./thread.aui";

// Editing a message loads its text into the composer, and the composer is
// the only place a message is written. These tests pin the behaviour around
// that: the composer carries no editing chrome, Escape cancels without
// sending, and an edit that changes nothing (or nothing at all) is not sent
// back to the model.

const run = vi.fn(async () => ({ content: [{ type: "text" as const, text: "ok" }] }));
const adapter: ChatModelAdapter = { run };

// The user message must be the LAST one: the action bar autohides (and
// renders no controls) on any message that is not the last one.
const MESSAGES: ThreadMessageLike[] = [
  { role: "user", content: [{ type: "text", text: "original question" }] },
];

function Harness() {
  const runtime = useLocalRuntime(adapter, { initialMessages: MESSAGES });
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
  return { host, unmount: () => act(() => root.unmount()) };
}

function composerText(host: HTMLElement): HTMLTextAreaElement {
  const input = host.querySelector<HTMLTextAreaElement>(".aui-composer-input");
  if (!input) throw new Error("composer textarea not found");
  return input;
}

async function startEdit(host: HTMLElement) {
  const button = host.querySelector<HTMLButtonElement>(".aui-user-action-edit");
  if (!button) throw new Error("edit control not found");
  await act(async () => {
    button.click();
  });
}

async function typeInto(host: HTMLElement, text: string) {
  const input = composerText(host);
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    setter?.call(input, text);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function submit(host: HTMLElement) {
  const form = host.querySelector("form");
  if (!form) throw new Error("composer form not found");
  await act(async () => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
}

async function pressEscape(host: HTMLElement) {
  const input = composerText(host);
  await act(async () => {
    input.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
    );
  });
}

beforeEach(() => {
  run.mockClear();
});

afterEach(() => {
  document.body.replaceChildren();
});

describe("edit-in-composer guards", () => {
  it("ignores an empty, whitespace-only or unchanged edit", () => {
    expect(shouldCommitEdit("original", "")).toBe(false);
    expect(shouldCommitEdit("original", "   \n  ")).toBe(false);
    expect(shouldCommitEdit("original", "original")).toBe(false);
    expect(shouldCommitEdit("original", "original  ")).toBe(false);
    expect(shouldCommitEdit("original", "changed")).toBe(true);
    expect(isUnchangedEdit("original", "original")).toBe(true);
  });
});

describe("edit-in-composer", () => {
  it("shows no editing chrome: the composer is a normal text box", async () => {
    const { host, unmount } = await mount();
    await startEdit(host);

    expect(composerText(host).value).toBe("original question");
    expect(host.querySelector('[data-slot="aui_composer-editing"]')).toBeNull();
    expect(host.querySelector('button[aria-label="Cancel edit"]')).toBeNull();

    unmount();
  });

  it("escape cancels the edit and sends nothing", async () => {
    const { host, unmount } = await mount();
    await startEdit(host);
    await pressEscape(host);

    expect(composerText(host).value).toBe("");
    expect(run).not.toHaveBeenCalled();

    unmount();
  });

  it("does not resend an edit whose text is identical", async () => {
    const { host, unmount } = await mount();
    await startEdit(host);
    await typeInto(host, "original question");
    await submit(host);

    expect(run).not.toHaveBeenCalled();

    unmount();
  });

  it("ignores an edit with nothing but spaces", async () => {
    const { host, unmount } = await mount();
    await startEdit(host);
    await typeInto(host, "   ");
    await submit(host);

    expect(run).not.toHaveBeenCalled();

    unmount();
  });

  it("sends an edit that actually changes the message", async () => {
    const { host, unmount } = await mount();
    await startEdit(host);
    await typeInto(host, "a different question");
    await submit(host);

    await vi.waitFor(() => expect(run).toHaveBeenCalledTimes(1));

    unmount();
  });
});
