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
    ...over,
  };
}

function mountHost() {
  const wrap = document.createElement("div");
  wrap.setAttribute("data-thread-skin", "digichat");
  wrap.innerHTML = `<div class="aui-composer-root"></div>`;
  document.body.appendChild(wrap);
}

describe("composer palette sync", () => {
  beforeEach(mountHost);
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("writes /language English when that row is chosen and filters as the user types", async () => {
    const user = userEvent.setup();
    const api = prefs({ paletteQuery: "eng" });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="language" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.getByRole("menuitemradio", { name: /en\s+English/i })).toBeTruthy();
    expect(screen.queryByRole("menuitemradio", { name: /nl\s+Dutch/i })).toBeNull();

    api.paletteQuery = "";
    document.body.replaceChildren();
    mountHost();
    const open = prefs();
    render(
      <EmbedChatPrefsProvider value={open}>
        <EmbedComposerMenu kind="language" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    await user.click(screen.getByRole("menuitemradio", { name: /en\s+English/i }));
    expect(open.setLanguage).toHaveBeenCalledWith("en");
    expect(open.setComposerDraft).toHaveBeenCalledWith("/language English");
  });

  it("writes the theme row the arrow lands on", async () => {
    const user = userEvent.setup();
    const api = prefs();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="theme" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    await user.keyboard("{ArrowDown}");
    expect(api.setComposerDraft).toHaveBeenCalledWith(expect.stringMatching(/^\/theme /));
  });

  it("lists foundry tools read-only", async () => {
    const user = userEvent.setup();
    const api = prefs({
      toolControl: "agent",
      catalogTools: [
        { id: "file_search", label: "Search" },
        {
          id: "records",
          label: "Records",
          tools: [
            { id: "records_list", label: "List connections" },
            { id: "records_open", label: "Open item" },
          ],
        },
      ],
    });
    const { unmount } = render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.getByRole("menuitem", { name: /^Search/ })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: /Records/ })).toBeTruthy();
    expect(screen.getAllByText("Managed by the agent").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("menuitem", { name: /^Search/ }));
    expect(api.setExtraTool).not.toHaveBeenCalled();
    expect(api.setDigisearch).not.toHaveBeenCalled();
    unmount();

    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="mcp" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.getByRole("menuitem", { name: /Records/ })).toBeTruthy();
    expect(screen.getAllByText("Managed by the agent").length).toBeGreaterThan(0);
  });

  it("lists OCC tools and MCP servers without toggling them", async () => {
    const user = userEvent.setup();
    const api = prefs({
      toolControl: "locked",
      mcpServers: [
        { id: "desk", label: "Support tickets" },
        { id: "digisearch", label: "Help search" },
        { id: "digivault", label: "Knowledge vault" },
      ],
      allowAddMcp: true,
    });
    const { unmount } = render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.getByRole("menuitemcheckbox", { name: /Support tickets/ })).toBeTruthy();
    expect(screen.getByRole("menuitemcheckbox", { name: /Help search/ })).toBeTruthy();
    expect(screen.getByRole("menuitemcheckbox", { name: /Knowledge vault/ })).toBeTruthy();
    await user.click(screen.getByRole("menuitemcheckbox", { name: /Support tickets/ }));
    expect(api.setExtraTool).not.toHaveBeenCalled();
    unmount();

    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="mcp" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    await user.click(screen.getByRole("menuitem", { name: /Support tickets/ }));
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /mcp new/i })).toBeNull();
  });
});
