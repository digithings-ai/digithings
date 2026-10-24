// @vitest-environment happy-dom
"use client";

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
import {
  DEFAULT_EMBED_CHAT_PREFS,
  type EmbedChatPrefsApi,
} from "../stock/embed-chat-prefs";
import { DigichatComposerToolbar } from "./digichat-composer-toolbar";

// The context meter reads thread state through @assistant-ui/react. The
// provider chip does not depend on it; the meter only has to render.
vi.mock("@assistant-ui/react", async () => {
  const actual = await vi.importActual<typeof import("@assistant-ui/react")>(
    "@assistant-ui/react",
  );
  return {
    ...actual,
    useAuiState: (selector: (state: unknown) => unknown) =>
      selector({ thread: { messages: [] as unknown[] } }),
  };
});

function prefsApi(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  const noop = () => {};
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS },
    setWebSearch: noop,
    setDigisearch: noop,
    setVault: noop,
    setExtraTool: noop,
    extraToolOn: () => true,
    setMcpConfig: noop,
    removeMcpConfig: noop,
    setLanguage: noop,
    setToolbar: noop,
    setScrollbars: noop,
    setDensity: noop,
    setScroll: noop,
    setView: noop,
    setThinking: noop,
    setModel: noop,
    setEffort: noop,
    setSearchEngine: noop,
    reset: noop,
    tenantAllowsWeb: true,
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
    sessionKey: "test-session",
    openSettings: noop,
    openHelp: noop,
    openTools: noop,
    openMcp: noop,
    openByok: noop,
    openModels: noop,
    openEffort: noop,
    openSearchEngine: noop,
    openView: noop,
    openDensity: noop,
    openThinking: noop,
    openLanguage: noop,
    openSessions: noop,
    openArtifacts: noop,
    newThread: noop,
    compactThread: noop,
    undo: noop,
    redo: noop,
    ...over,
  };
}

describe("DigichatComposerToolbar provider chip (#4597)", () => {
  it("names the backend without a button when the BYOK preference is off", () => {
    // A tenant that cannot switch providers still says which backend serves
    // it — a Foundry tenant is Azure AI Foundry, not the house provider. The
    // name is a label: there is no provider menu to open.
    const { container } = render(
      <DigichatComposerToolbar
        prefs={prefsApi({ showByok: false, providerLabel: "openrouter" })}
      />,
    );
    expect(screen.queryByLabelText("Open provider menu")).toBeNull();
    expect(container.textContent).toContain("openrouter");
    // The name keeps its separator: the row still reads
    // "backend / MCP / tools / EN".
    expect(container.querySelectorAll(".aui-composer-meta-sep").length).toBeGreaterThan(0);
  });

  it("shows the backend the host named", () => {
    render(
      <DigichatComposerToolbar
        prefs={prefsApi({ showByok: true, providerLabel: "openrouter" })}
      />,
    );
    expect(screen.getByLabelText("Open provider menu").textContent).toBe(
      "openrouter",
    );
  });

  it("hides the provider chip when the host named no backend", () => {
    const { container } = render(
      <DigichatComposerToolbar prefs={prefsApi({ showByok: true })} />,
    );
    expect(screen.queryByLabelText("Open provider menu")).toBeNull();
    expect(container.querySelectorAll(".aui-composer-meta-sep")).toHaveLength(1);
  });

  it("never shows a blank backend name", () => {
    render(
      <DigichatComposerToolbar
        prefs={prefsApi({ showByok: true, providerLabel: "   " })}
      />,
    );
    expect(screen.queryByLabelText("Open provider menu")).toBeNull();
  });

  it("never starts the row with a separator when there is no model", () => {
    // A tenant with no model list (a Foundry agent) has no model chip, so the
    // row must not open with a dangling slash.
    const { container } = render(
      <DigichatComposerToolbar
        prefs={prefsApi({ showModels: false, providerLabel: "cheaperinference" })}
      />,
    );
    const row = container.querySelector('[data-slot="aui_composer-toolbar-inner"]');
    const first = row?.firstElementChild;
    expect(first?.className).not.toMatch(/aui-composer-meta-sep/);
    expect((row?.textContent ?? "").trim().startsWith("/")).toBe(false);
  });

  it("sizes the context meter without labeling that window as the selected model", () => {
    render(
      <DigichatComposerToolbar
        prefs={prefsApi({
          showModels: true,
          showContextMeter: true,
          prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "" },
          meterModel: "deepseek/deepseek-v4.1-flash-1017",
        })}
      />,
    );
    expect(screen.getByLabelText("Open models").textContent).toBe("auto");
    expect(screen.getByRole("img", { name: /^Context / })).toBeTruthy();
  });

  it("hides the context meter unless the host enabled it", () => {
    const { container } = render(
      <DigichatComposerToolbar
        prefs={prefsApi({
          meterModel: "deepseek/deepseek-v4.1-flash-1017",
        })}
      />,
    );
    expect(container.querySelector(".aui-context-meter")).toBeNull();
  });

  it("sizes the bar to the turn model, not the session model", () => {
    render(
      <DigichatComposerToolbar
        prefs={prefsApi({
          showContextMeter: true,
          prefs: {
            ...DEFAULT_EMBED_CHAT_PREFS,
            model: "deepseek/deepseek-v4.1-flash-1017",
          },
          meterModel: "z-ai/glm-4.7-flash",
        })}
      />,
    );
    expect(screen.getByLabelText("Open models").textContent).toBe(
      "deepseek/deepseek-v4.1-flash-1017",
    );
    expect(screen.getByRole("img", { name: "Context 0 / 200.0k tokens" })).toBeTruthy();
  });

  it("gates the provider chip on its own preference, not the model chip's", () => {
    render(
      <DigichatComposerToolbar
        prefs={prefsApi({
          showByok: true,
          showModels: false,
          providerLabel: "openrouter",
        })}
      />,
    );
    expect(screen.getByLabelText("Open provider menu").textContent).toBe(
      "openrouter",
    );
  });
});

describe("DigichatComposerToolbar usage meter", () => {
  it("draws the gate's turn budget in place of the context meter", () => {
    const { container } = render(
      <DigichatComposerToolbar
        prefs={prefsApi({
          showContextMeter: true,
          meterModel: "deepseek/deepseek-v4.1-flash-1017",
          usage: { used: 1, limit: 3 },
        })}
      />,
    );
    expect(screen.getByTestId("embed-usage-meter")).toBeTruthy();
    // One meter in the slot, never two.
    expect(screen.queryByRole("img", { name: /^Context / })).toBeNull();
    expect(container.querySelectorAll(".aui-usage-meter")).toHaveLength(1);
  });

  it("keeps the context meter when the tenant has no gate", () => {
    render(
      <DigichatComposerToolbar
        prefs={prefsApi({
          showContextMeter: true,
          meterModel: "deepseek/deepseek-v4.1-flash-1017",
        })}
      />,
    );
    expect(screen.queryByTestId("embed-usage-meter")).toBeNull();
    expect(screen.getByRole("img", { name: /^Context / })).toBeTruthy();
  });

  it("falls back to the context meter when a gate reports no budget", () => {
    // A limit of 0 is not a meter; blanking the slot would hide the context
    // bar for a reading that means "no gate".
    render(
      <DigichatComposerToolbar
        prefs={prefsApi({
          showContextMeter: true,
          meterModel: "deepseek/deepseek-v4.1-flash-1017",
          usage: { used: 0, limit: 0 },
        })}
      />,
    );
    expect(screen.queryByTestId("embed-usage-meter")).toBeNull();
    expect(screen.getByRole("img", { name: /^Context / })).toBeTruthy();
  });
});
