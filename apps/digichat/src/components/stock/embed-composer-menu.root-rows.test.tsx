// @vitest-environment happy-dom
"use client";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmbedComposerMenu } from "./embed-composer-menu";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  type EmbedChatPrefsApi,
} from "@digithings/ui/chat/stock";

function prefs(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS },
    setWebSearch: vi.fn(),
    setDigisearch: vi.fn(),
    setVault: vi.fn(),
    setExtraTool: vi.fn(),
    extraToolOn: () => true,
    setMcpConfig: vi.fn(),
    removeMcpConfig: vi.fn(),
    setLanguage: vi.fn(),
    setView: vi.fn(),
    setThinking: vi.fn(),
    setModel: vi.fn(),
    setEffort: vi.fn(),
    setSearchEngine: vi.fn(),
    setToolbar: vi.fn(),
    setScrollbars: vi.fn(),
    setDensity: vi.fn(),
    reset: vi.fn(),
    tenantAllowsWeb: false,
    showByok: false,
    showModels: true,
    hasDigisearch: false,
    hasVault: false,
    hasSessions: false,
    hasArtifacts: false,
    allowUserMcp: false,
    allowAddMcp: false,
    catalogTools: [],
    mcpServers: [],
    sessionKey: "t",
    openSettings: vi.fn(),
    openHelp: vi.fn(),
    openTools: vi.fn(),
    openMcp: vi.fn(),
    openByok: vi.fn(),
    openModels: vi.fn(),
    openEffort: vi.fn(),
    openSearchEngine: vi.fn(),
    openView: vi.fn(),
    openDensity: vi.fn(),
    openThinking: vi.fn(),
    openLanguage: vi.fn(),
    openSessions: vi.fn(),
    openArtifacts: vi.fn(),
    newThread: vi.fn(),
    compactThread: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    setComposerDraft: vi.fn(),
    composerDraftBound: true,
    ...over,
  };
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

  it("offers no row the app cannot run", () => {
    render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    // /copy, /export md and /export html act on the chat state, which the
    // app-level menu does not hold. A row it cannot run closes the menu and
    // does nothing, so the menu does not offer it.
    expect(screen.queryByRole("menuitem", { name: /^\/copy/i })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /^\/export/i })).toBeNull();
  });

  it("still offers and runs the rows it can run", async () => {
    const user = userEvent.setup();
    const api = prefs();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.getByRole("menuitem", { name: /^\/new/i })).toBeTruthy();
    await user.click(screen.getByRole("menuitem", { name: /^\/new/i }));
    expect(api.newThread).toHaveBeenCalled();
  });
});
