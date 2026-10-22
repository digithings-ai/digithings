// @vitest-environment happy-dom
"use client";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmbedComposerMenu } from "./embed-composer-menu";
import { spyFixture } from "@/lib/embed-chat-prefs.fixture";
import { EmbedChatPrefsProvider, type EmbedChatPrefsApi } from "@digithings/ui/chat/stock";

function prefs(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return spyFixture(vi.fn, over);
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
    expect(screen.getByRole("menuitem", { name: /^\/file_search/ })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: /^\/records/ })).toBeTruthy();
    expect(screen.getAllByText("Managed by the agent").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("menuitem", { name: /^\/file_search/ }));
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
    await user.click(screen.getByRole("menuitem", { name: /Support tickets/ }));
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
        ├─ search                  On
        └─ fetch_all               On
      /digivault                   On
        ├─ search_notes            On
        └─ get_note                On
      /desk                        On
        ├─ search_tickets          On
        ├─ get_ticket              Off
        └─ ticket_report           On"
    `);
  });

  it("keeps the tree when the agent owns the tools", () => {
    const api = prefs({ toolControl: "agent", hasDigisearch: true, hasVault: true, mcpServers: servers });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(toolsTree()).toMatchInlineSnapshot(`
      "/digisearch                  Managed by the agent
        ├─ search                  Managed by the agent
        └─ fetch_all               Managed by the agent
      /digivault                   Managed by the agent
        ├─ search_notes            Managed by the agent
        └─ get_note                Managed by the agent
      /desk                        Managed by the agent
        ├─ search_tickets          Managed by the agent
        ├─ get_ticket              Managed by the agent
        └─ ticket_report           Managed by the agent"
    `);
    expect(screen.queryAllByRole("menuitemcheckbox")).toHaveLength(0);
  });

  it("toggles a configured tool, and a built-in tool follows its service", async () => {
    const user = userEvent.setup();
    const api = prefs({ toolControl: "toggle", hasDigisearch: true, mcpServers: servers });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    await user.click(screen.getByRole("menuitemcheckbox", { name: /^get_ticket/ }));
    expect(api.setExtraTool).toHaveBeenCalledWith("desk_get_ticket", false);
    await user.click(screen.getByRole("menuitem", { name: /^fetch_all/ }));
    expect(api.setDigisearch).not.toHaveBeenCalled();
    expect(api.setExtraTool).toHaveBeenCalledTimes(1);
  });

  it("lists configured tools instead of the built-ins when the deployment names them", () => {
    const api = prefs({
      toolControl: "toggle",
      hasDigisearch: true,
      catalogTools: [{ id: "digisearch", label: "Search", tools: [{ id: "digisearch", label: "search_docs" }] }],
    });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="tools" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    expect(toolsTree()).toMatchInlineSnapshot(`
      "/digisearch                  On
        └─ search_docs             On"
    `);
  });
});
