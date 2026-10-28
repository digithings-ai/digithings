// @vitest-environment happy-dom
"use client";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmbedComposerMenu } from "./embed-composer-menu";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  type EmbedChatPrefsApi,
} from "@digithings/ui/chat/stock";
import { seedPrivateMode, setPrivateMode } from "@/lib/product-slash-commands";

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
    tenantAllowsWeb: true,
    showByok: false,
    showModels: true,
    hasDigisearch: true,
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

function rowValue(name: RegExp): string {
  const row = screen.getByRole("menuitem", { name });
  return row.querySelector("[data-slot='palette-value']")?.textContent ?? "";
}

describe("command palette value column", () => {
  beforeEach(() => {
    mountHost();
    seedPrivateMode({ tenantOptIn: true, urlPrivate: true });
  });
  afterEach(() => {
    document.body.replaceChildren();
    seedPrivateMode({ tenantOptIn: false, urlPrivate: false });
  });

  it("shows the current value on the right and the sentence only on the selected row", async () => {
    const user = userEvent.setup();
    render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="settings" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );

    expect(rowValue(/^\/view/)).toBe("balanced");
    expect(rowValue(/^\/effort/)).toBe("medium");
    expect(rowValue(/^\/models/)).toBe("auto");
    expect(rowValue(/^\/tools/)).toBe("on");
    expect(rowValue(/^\/private/)).toBe("on");

    const details = () => document.querySelectorAll("[data-slot='palette-detail']");
    expect(details()).toHaveLength(1);
    const selected = screen
      .getAllByRole("menuitem")
      .find((row) => row.getAttribute("aria-selected") === "true");
    expect(selected).toBeTruthy();
    const describedBy = selected?.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)?.textContent?.trim().endsWith(".")).toBe(true);
    for (const row of screen.getAllByRole("menuitem")) {
      if (row === selected) continue;
      expect(row.hasAttribute("aria-describedby")).toBe(false);
    }

    const privateRow = screen.getByRole("menuitem", { name: /^\/private/ });
    expect(privateRow.getAttribute("aria-selected")).toBe("false");
    let guard = 0;
    while (privateRow.getAttribute("aria-selected") !== "true" && guard < 40) {
      await user.keyboard("{ArrowDown}");
      guard += 1;
    }
    expect(privateRow.getAttribute("aria-selected")).toBe("true");
    expect(details()).toHaveLength(1);
    const privateDetail = document.getElementById(privateRow.getAttribute("aria-describedby")!);
    expect(privateDetail?.getAttribute("data-slot")).toBe("palette-detail");
    expect(privateDetail?.textContent).toBe(
      "Ask the model to use stand-in names in its replies.",
    );
    expect(privateRow.querySelector("[data-slot='palette-value']")?.className).toMatch(
      /justify-end/,
    );
  });

  it("reveals the description on the first phone tap and runs the row on the second", () => {
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    const privateRow = screen.getByRole("menuitem", { name: /^\/private/ });
    expect(privateRow.getAttribute("aria-selected")).toBe("false");

    fireEvent.pointerDown(privateRow, { pointerType: "touch" });
    fireEvent.click(privateRow);

    expect(privateRow.getAttribute("aria-selected")).toBe("true");
    expect(onClose).not.toHaveBeenCalled();
    expect(document.getElementById(privateRow.getAttribute("aria-describedby")!)?.textContent).toMatch(
      /stand-in/,
    );

    fireEvent.pointerDown(privateRow, { pointerType: "touch" });
    fireEvent.click(privateRow);
    expect(onClose).toHaveBeenCalledTimes(1);
    setPrivateMode(false);
  });
});
