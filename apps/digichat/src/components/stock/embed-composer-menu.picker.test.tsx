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

/** Navigated row: the user-message chevron on the left. */
function hasChevron(row: HTMLElement): boolean {
  return (row.querySelector(".aui-menu-cursor")?.childElementCount ?? 0) > 0;
}

/** Configured value: the 3x3 cube diamond on the right. */
function hasDiamond(row: HTMLElement): boolean {
  return row.querySelector("[data-slot='dropdown-menu-radio-item-indicator']") !== null;
}

function prefs(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "alpha" },
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
    openHelp: vi.fn(),
    openTools: vi.fn(),
    openMcp: vi.fn(),
    openByok: vi.fn(),
    openModels: vi.fn(),
    openEffort: vi.fn(),
    openSearchEngine: vi.fn(),
    openView: vi.fn(),
    openThinking: vi.fn(),
    openLanguage: vi.fn(),
    openSessions: vi.fn(),
    newThread: vi.fn(),
    compactThread: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    ...over,
  };
}

function mountHost() {
  const wrap = document.createElement("div");
  wrap.setAttribute("data-thread-skin", "digichat");
  wrap.setAttribute("data-picker-test-host", "true");
  wrap.innerHTML = `<div class="aui-composer-root"></div>`;
  document.body.appendChild(wrap);
}

describe("EmbedComposerMenu exclusive pickers", () => {
  beforeEach(mountHost);
  afterEach(() => {
    document.querySelector("[data-picker-test-host]")?.remove();
  });

  it("applies a model on click and closes; selected row uses the diamond, not on", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu
          kind="models"
          models={["alpha", "beta"]}
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );

    const selected = await screen.findByRole("menuitemradio", { name: "alpha" });
    expect(selected).toHaveAttribute("aria-checked", "true");
    expect(selected.textContent).not.toMatch(/\bon\b/i);
    expect(hasChevron(selected)).toBe(false);
    expect(hasDiamond(selected)).toBe(true);

    const other = screen.getByRole("menuitemradio", { name: "beta" });
    expect(hasChevron(other)).toBe(false);
    expect(hasDiamond(other)).toBe(false);

    // The chevron follows hover / arrow keys; the configured value keeps its
    // diamond, so the two marks mean different things.
    await user.hover(other);
    expect(hasChevron(other)).toBe(true);
    expect(hasChevron(selected)).toBe(false);
    expect(hasDiamond(selected)).toBe(true);
    expect(hasDiamond(other)).toBe(false);

    // Navigating the checked row does not add a chevron: the diamond stays
    // and remains the only mark on that row.
    await user.hover(selected);
    expect(hasChevron(selected)).toBe(false);
    expect(hasDiamond(selected)).toBe(true);

    await user.click(other);
    expect(api.setModel).toHaveBeenCalledWith("beta");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("applies a model on Enter and closes", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu
          kind="models"
          models={["alpha", "beta"]}
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );

    await screen.findByRole("menuitemradio", { name: "alpha" });
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");
    expect(api.setModel).toHaveBeenCalledWith("beta");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("applies a model on ArrowRight and closes", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu
          kind="models"
          models={["alpha", "beta"]}
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );

    await screen.findByRole("menuitemradio", { name: "alpha" });
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{ArrowRight}");
    expect(api.setModel).toHaveBeenCalledWith("beta");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes language pick on click and marks the current code with the diamond", async () => {
    const user = userEvent.setup();
    const api = prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, language: "en", model: "alpha" } });
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="language" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const english = await screen.findByRole("menuitemradio", { name: /en\s+English/i });
    expect(english).toHaveAttribute("aria-checked", "true");
    expect(english.textContent).not.toMatch(/\bon\b/i);
    expect(hasChevron(english)).toBe(false);
    expect(hasDiamond(english)).toBe(true);

    const dutch = screen.getByRole("menuitemradio", { name: /nl\s+Dutch/i });
    await user.click(dutch);
    expect(api.setLanguage).toHaveBeenCalledWith("nl");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes search-engine pick on click and marks the current engine with the chevron", async () => {
    const user = userEvent.setup();
    const api = prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, searchEngine: "auto" } });
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="search-engine" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const auto = await screen.findByRole("menuitemradio", { name: /search-engine auto/i });
    expect(auto).toHaveAttribute("aria-checked", "true");

    const exa = screen.getByRole("menuitemradio", { name: /search-engine exa/i });
    await user.click(exa);
    expect(api.setSearchEngine).toHaveBeenCalledWith("exa");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("hides the search-engine row on the main menu when the tenant disallows web", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs({ tenantAllowsWeb: false })}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.queryByText("/search-engine")).toBeNull();
    unmount();
  });

  it("shows the search-engine row on the main menu when the tenant allows web", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs({ tenantAllowsWeb: true })}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    expect(await screen.findByText("/search-engine")).not.toBeNull();
    unmount();
  });

  it("offers auto in /models when the deployment default is auto", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu
          kind="models"
          models={["alpha", "beta"]}
          defaultModel="auto"
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );
    expect(await screen.findByRole("menuitemradio", { name: /auto/ })).not.toBeNull();
    unmount();
  });

  it("does not offer auto when a model is pinned", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu
          kind="models"
          models={["alpha", "beta"]}
          defaultModel="alpha"
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );
    await screen.findByRole("menuitemradio", { name: "alpha" });
    expect(screen.queryByRole("menuitemradio", { name: /auto/ })).toBeNull();
    unmount();
  });

  it("lists cheaperinference as a provider choice", async () => {
    const onClose = vi.fn();
    const onClearProvider = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu
          kind="provider"
          onClose={onClose}
          onClearProvider={onClearProvider}
        />
      </EmbedChatPrefsProvider>,
    );
    expect(
      await screen.findByRole("menuitemradio", { name: /cheaperinference/ }),
    ).not.toBeNull();
    unmount();
  });

  it("renders the /help panel with examples, commands and the contact address", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="help" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    const panel = await screen.findByText(/Ask about OCC policies/);
    expect(panel).not.toBeNull();
    expect(screen.getByText(/How do I raise a support ticket\?/)).not.toBeNull();
    expect(screen.getByText(/\/models/)).not.toBeNull();
    const contact = screen.getByRole("link", { name: "contact@digithings.ai" });
    expect(contact.getAttribute("href")).toBe("mailto:contact@digithings.ai");
    unmount();
  });
});
