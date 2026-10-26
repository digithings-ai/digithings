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
    setScroll: vi.fn(),
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

  it("flips scroll follow/free from the main palette, naming the state it switches to", async () => {
    const user = userEvent.setup();
    const api = prefs();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    const toFree = await screen.findByRole("menuitemcheckbox", { name: /scroll free/i });
    await user.click(toFree);
    expect(api.setScroll).toHaveBeenCalledWith("free");

    document.body.replaceChildren();
    mountHost();
    const free = prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, scroll: "free" } });
    render(
      <EmbedChatPrefsProvider value={free}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    const toFollow = await screen.findByRole("menuitemcheckbox", { name: /scroll follow/i });
    await user.click(toFollow);
    expect(free.setScroll).toHaveBeenCalledWith("follow");
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

  it("toggles a tool from /tools on an unlocked host", async () => {
    const user = userEvent.setup();
    const api = prefs({ toolControl: "toggle", hasDigisearch: true });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    await user.click(screen.getByRole("menuitemcheckbox", { name: /^\/digisearch/ }));
    expect(api.setDigisearch).toHaveBeenCalledWith(!api.prefs.digisearch);
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
    const fileSearch = screen.getByRole("menuitemcheckbox", { name: /^\/file_search/ });
    expect(fileSearch.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("menuitemcheckbox", { name: /^\/records/ })).toBeTruthy();
    expect(screen.queryByText(/managed by the agent/i)).toBeNull();
    await user.click(fileSearch);
    expect(api.setExtraTool).not.toHaveBeenCalled();
    expect(api.setDigisearch).not.toHaveBeenCalled();
    unmount();

    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="mcp" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.getByRole("menuitem", { name: /^records/ })).toBeTruthy();
    expect(screen.queryByText(/managed by the agent/i)).toBeNull();
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
    expect(screen.getByRole("menuitemcheckbox", { name: /^\/desk/ })).toBeTruthy();
    expect(screen.getByRole("menuitemcheckbox", { name: /^\/digisearch/ })).toBeTruthy();
    expect(screen.getByRole("menuitemcheckbox", { name: /^\/digivault/ })).toBeTruthy();
    await user.click(screen.getByRole("menuitemcheckbox", { name: /^\/desk/ }));
    expect(api.setExtraTool).not.toHaveBeenCalled();
    unmount();

    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="mcp" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    await user.click(screen.getByRole("menuitem", { name: /^desk/ }));
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("menuitem", { name: /mcp new/i })).toBeNull();
  });
});

/** The /tools page as text: one line per row, the branch glyph, label and value. */
function toolsTree(): string {
  return Array.from(document.querySelectorAll<HTMLElement>("button[id^='dc-menu-']"))
    .map((row) => {
      const glyph = row.querySelector("[data-slot='tools-tree-branch']")?.textContent ?? "";
      const label = row.querySelector("span.flex-1")?.textContent ?? "";
      const value = row.querySelector("span.ml-auto")?.textContent ?? "";
      const left = glyph ? `  ${glyph} ${label}` : label;
      return `${left.padEnd(28)} ${value}`.trimEnd();
    })
    .join("\n");
}

describe("/tools tree", () => {
  beforeEach(mountHost);
  afterEach(() => {
    document.body.replaceChildren();
  });

  const servers = [
    {
      id: "desk",
      label: "Support tickets",
      tools: [
        { id: "desk_search_tickets", label: "search_tickets" },
        { id: "desk_get_ticket", label: "get_ticket" },
        { id: "desk_ticket_report", label: "ticket_report" },
      ],
    },
  ];

  it("lists each service as /slash with its tools under it", () => {
    const api = prefs({
      toolControl: "toggle",
      hasDigisearch: true,
      hasVault: true,
      mcpServers: servers,
      extraToolOn: (id: string) => id !== "desk_get_ticket",
    });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(toolsTree()).toMatchInlineSnapshot(`
      "/digisearch                  On
        ├─ digisearch              On
        └─ digisearch_fetch_all    On
      /digivault                   On
        ├─ digivault_search_notes  On
        └─ digivault_get_note      On
      /desk                        On
        ├─ desk_search_tickets     On
        ├─ desk_get_ticket         Off
        └─ desk_ticket_report      On"
    `);
  });

  it("keeps one row per id when the capability and an MCP server share it", () => {
    // The duplicate digisearch/digivault row: the capability pushes a service
    // row and the same id also arrives from mcpServers. One backend id, one row.
    const api = prefs({
      toolControl: "toggle",
      hasDigisearch: true,
      hasVault: true,
      mcpServers: [
        { id: "digisearch", label: "Help search" },
        { id: "digivault", label: "Knowledge vault" },
      ],
    });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.getAllByRole("menuitemcheckbox", { name: /^\/digisearch/ })).toHaveLength(1);
    expect(screen.getAllByRole("menuitemcheckbox", { name: /^\/digivault/ })).toHaveLength(1);
    // The surviving row still carries the service's tools.
    expect(screen.getByRole("menuitem", { name: /^digisearch_fetch_all/ })).toBeTruthy();
  });

  it("keeps the tree when the agent owns the tools", () => {
    const api = prefs({ toolControl: "agent", hasDigisearch: true, hasVault: true, mcpServers: servers });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(toolsTree()).toMatchInlineSnapshot(`
      "/digisearch                  On
        ├─ digisearch              On
        └─ digisearch_fetch_all    On
      /digivault                   On
        ├─ digivault_search_notes  On
        └─ digivault_get_note      On
      /desk                        On
        ├─ desk_search_tickets     On
        ├─ desk_get_ticket         On
        └─ desk_ticket_report      On"
    `);
    const switches = screen.queryAllByRole("menuitemcheckbox");
    expect(switches.length).toBeGreaterThan(0);
    expect(switches.every((row) => row.getAttribute("aria-checked") === "true")).toBe(true);
  });

  it("shows tool names only, without a note in parentheses", () => {
    const api = prefs({
      toolControl: "locked",
      mcpServers: [
        {
          id: "search",
          label: "Help search (help docs)",
          tools: [
            { id: "search_help", label: "search_help (help docs)" },
            { id: "search_older", label: "search_older (past tickets)" },
          ],
        },
      ],
    });
    const { unmount } = render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(toolsTree()).toMatchInlineSnapshot(`
      "/search                      On
        ├─ search_help             On
        └─ search_older            On"
    `);
    unmount();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="mcp" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.getByRole("menuitem", { name: /^search/ })).toBeTruthy();
    expect(document.body.textContent ?? "").not.toMatch(/\(help docs\)|\(past tickets\)/);
  });

  it("toggles a configured tool, and a built-in tool follows its service", async () => {
    const user = userEvent.setup();
    const api = prefs({ toolControl: "toggle", hasDigisearch: true, mcpServers: servers });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    await user.click(screen.getByRole("menuitemcheckbox", { name: /^desk_get_ticket/ }));
    expect(api.setExtraTool).toHaveBeenCalledWith("desk_get_ticket", false);
    await user.click(screen.getByRole("menuitem", { name: /^digisearch_fetch_all/ }));
    expect(api.setDigisearch).not.toHaveBeenCalled();
    expect(api.setExtraTool).toHaveBeenCalledTimes(1);
  });

  it("lists configured tools instead of the built-ins when the deployment names them", () => {
    const api = prefs({
      toolControl: "toggle",
      hasDigisearch: true,
      catalogTools: [
        {
          id: "digisearch",
          label: "Search",
          // The tool row shows the backend id, so the fixture carries a real
          // one rather than reusing the server id.
          tools: [{ id: "digisearch_search_docs", label: "search_docs" }],
        },
      ],
    });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(toolsTree()).toMatchInlineSnapshot(`
      "/digisearch                  On
        └─ digisearch_search_docs  On"
    `);
  });
});
