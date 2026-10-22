// @vitest-environment happy-dom
"use client";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmbedComposerMenu } from "./embed-composer-menu";
import { prefsFixture } from "@/lib/embed-chat-prefs.fixture";
import { EmbedChatPrefsProvider } from "@digithings/ui/chat/stock";

/** The ids of the rows the menu renders (the row id is its command id). */
function renderedRowIds(): string[] {
  return screen.getAllByRole("menuitem").map((item) => item.id.replace(/^dc-menu-/, ""));
}

describe("the composer root menu", () => {
  beforeEach(() => {
    const wrap = document.createElement("div");
    wrap.setAttribute("data-thread-skin", "digichat");
    wrap.innerHTML = `<div class="aui-composer-root"></div>`;
    document.body.appendChild(wrap);
  });

  afterEach(() => {
    document.body.replaceChildren();
  });

  it("renders its rows", () => {
    render(
      <EmbedChatPrefsProvider value={prefsFixture()}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    // Without this the absence assertions below would pass on an empty menu.
    expect(screen.getAllByRole("menuitem").length).toBeGreaterThan(0);
  });

  it("offers no row the app cannot run", () => {
    render(
      <EmbedChatPrefsProvider value={prefsFixture()}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    // /copy, /export md and /export html act on the chat state, which the
    // app-level menu does not hold. /compact reads the thread to summarise it.
    // /undo had no runner at all. A row the menu cannot run closes the menu
    // and does nothing, so the menu does not offer it.
    const withheld = [/^\/copy/i, /^\/export/i, /^\/compact/i, /^\/undo/i];
    for (const name of withheld) {
      expect(screen.queryByRole("menuitem", { name })).toBeNull();
    }
  });

  it("offers exactly the rows it can run", () => {
    render(
      <EmbedChatPrefsProvider value={prefsFixture()}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    // The set is pinned: a row that appears here must be one the runner can
    // run, and a row that disappears must be one it cannot.
    expect(renderedRowIds().sort()).toEqual([
      "clear",
      "density",
      "dutch",
      "effort",
      "english",
      "french",
      "help",
      "italian",
      "language",
      "models",
      "new",
      "redo",
      "scrollbar",
      "spanish",
      "theme",
      "thinking",
      "toolbar",
      "view",
    ]);
  });

  it("withholds /new and /clear from a host that cannot start a conversation", () => {
    render(
      <EmbedChatPrefsProvider value={prefsFixture({ hasNewThread: false })}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.queryByRole("menuitem", { name: /^\/new/i })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /^\/clear/i })).toBeNull();
  });

  it("withholds /redo from a host that cannot regenerate the last answer", () => {
    render(
      <EmbedChatPrefsProvider value={prefsFixture({ hasRedo: false })}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.queryByRole("menuitem", { name: /^\/redo/i })).toBeNull();
  });

  it("still offers and runs the rows it can run", async () => {
    const user = userEvent.setup();
    const newThread = vi.fn();
    const api = prefsFixture({ newThread });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.getByRole("menuitem", { name: /^\/new/i })).toBeTruthy();
    await user.click(screen.getByRole("menuitem", { name: /^\/new/i }));
    expect(newThread).toHaveBeenCalled();
  });
});
