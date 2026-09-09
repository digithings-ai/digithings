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
} from "./embed-chat-prefs";

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
    setThinking: vi.fn(),
    setModel: vi.fn(),
    setEffort: vi.fn(),
    reset: vi.fn(),
    tenantAllowsWeb: true,
    showByok: true,
    showModels: true,
    hasDigisearch: true,
    hasVault: true,
    hasSessions: false,
    allowUserMcp: true,
    allowAddMcp: true,
    catalogTools: [],
    mcpServers: [],
    sessionKey: "t",
    openSettings: vi.fn(),
    openTools: vi.fn(),
    openMcp: vi.fn(),
    openByok: vi.fn(),
    openModels: vi.fn(),
    openEffort: vi.fn(),
    openLanguage: vi.fn(),
    openSessions: vi.fn(),
    newThread: vi.fn(),
    compactThread: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    ...over,
  };
}

describe("EmbedComposerMenu /mcp id dropdown", () => {
  beforeEach(() => {
    const wrap = document.createElement("div");
    wrap.setAttribute("data-thread-skin", "digichat");
    wrap.setAttribute("data-mcp-test-host", "true");
    wrap.innerHTML = `<div class="aui-composer-root"></div>`;
    document.body.appendChild(wrap);
  });

  afterEach(() => {
    document.querySelector("[data-mcp-test-host]")?.remove();
  });

  it("opens a compact in-menu catalog on id focus and closes on Escape", async () => {
    const user = userEvent.setup();
    render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="mcp" mcpSeed="new" onClose={() => {}} />
      </EmbedChatPrefsProvider>,
    );

    const id = await screen.findByRole("combobox");
    expect(document.querySelector("[data-mcp-id-dropdown]")).toBeNull();
    expect(document.querySelector("datalist")).toBeNull();

    await user.click(id);
    const list = document.querySelector("[data-mcp-id-dropdown]");
    expect(list).toBeTruthy();
    expect(list?.className).toMatch(/absolute/);
    expect(list?.className).toMatch(/max-h-40/);
    expect(list?.className).toMatch(/overflow-y-auto/);
    expect(list?.className).not.toMatch(/fixed/);
    expect(screen.getByRole("dialog", { name: /mcp/i })).toBeTruthy();
    expect(screen.getByText("productivity")).toBeTruthy();
    expect(screen.getByRole("option", { name: "linear" })).toBeTruthy();

    await user.keyboard("{Escape}");
    expect(document.querySelector("[data-mcp-id-dropdown]")).toBeNull();
    expect(screen.getByRole("combobox")).toBeTruthy();
    expect(screen.getByText("other")).toBeTruthy();
  });

  it("applies a catalog row from the open dropdown", async () => {
    const user = userEvent.setup();
    const setMcpConfig = vi.fn();
    render(
      <EmbedChatPrefsProvider value={prefs({ setMcpConfig })}>
        <EmbedComposerMenu kind="mcp" mcpSeed="new" onClose={() => {}} />
      </EmbedChatPrefsProvider>,
    );

    await user.click(await screen.findByRole("combobox"));
    await user.click(screen.getByRole("option", { name: "linear" }));
    expect(document.querySelector("[data-mcp-id-dropdown]")).toBeNull();
    expect(setMcpConfig).toHaveBeenCalled();
    const draft = setMcpConfig.mock.calls.at(-1)?.[0] as { id?: string; url?: string };
    expect(draft.id).toBe("linear");
    expect(draft.url).toBe("https://mcp.linear.app/mcp");
    expect(screen.getByText("Authenticate")).toBeTruthy();
    expect(screen.getByText("or")).toBeTruthy();
    expect(screen.getByPlaceholderText("OAuth token")).toBeTruthy();
  });

  it("closes the catalog on blur outside the id field", async () => {
    const user = userEvent.setup();
    render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="mcp" mcpSeed="new" onClose={() => {}} />
      </EmbedChatPrefsProvider>,
    );

    await user.click(await screen.findByRole("combobox"));
    expect(document.querySelector("[data-mcp-id-dropdown]")).toBeTruthy();
    await user.click(screen.getByPlaceholderText("https://…"));
    expect(document.querySelector("[data-mcp-id-dropdown]")).toBeNull();
  });
});
