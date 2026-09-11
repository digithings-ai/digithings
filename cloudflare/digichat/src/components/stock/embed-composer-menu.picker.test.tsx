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
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "alpha" },
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

  it("applies a model on click and closes; selected row uses the radio disc, not on", async () => {
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
    expect(selected.querySelector("[data-slot='dropdown-menu-radio-item-indicator']")).not.toBeNull();

    const other = screen.getByRole("menuitemradio", { name: "beta" });
    expect(other.querySelector("[data-slot='dropdown-menu-radio-item-indicator']")).toBeNull();
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

  it("closes language pick on click and marks the current code with the radio disc", async () => {
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
    expect(english.querySelector("[data-slot='dropdown-menu-radio-item-indicator']")).not.toBeNull();

    const dutch = screen.getByRole("menuitemradio", { name: /nl\s+Dutch/i });
    await user.click(dutch);
    expect(api.setLanguage).toHaveBeenCalledWith("nl");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
