// @vitest-environment happy-dom
"use client";

/**
 * Force-web arm is tenant-gated (#3871): a deny tenant (datatap-shape,
 * tenantAllowsWeb false) typing `/websearch foo` must not set the pending
 * web-search flag, while an allowed tenant still arms this-send web search.
 * The BFF deny stays as backstop; this pins the client arm point.
 */

import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { SkinChromeProvider, DEFAULT_SKIN_CHROME } from "@/components/stock/skin-chrome";
import {
  EmbedChatPrefsProvider,
  DEFAULT_EMBED_CHAT_PREFS,
  type EmbedChatPrefsApi,
} from "@/components/stock/embed-chat-prefs";
import { takePendingWebSearchForce } from "@/lib/pending-chat-headers";
import { DigichatSkin } from "./digichat";
const composerState = vi.hoisted(() => ({ text: "" }));
const capture = vi.hoisted(() => ({
  submit: null as null | ((event: { preventDefault: () => void }) => void),
}));

vi.mock("@assistant-ui/react", async () => {
  const actual = await vi.importActual<typeof import("@assistant-ui/react")>(
    "@assistant-ui/react",
  );
  const aui = {
    composer: {
      getState: () => ({ text: composerState.text }),
      setText: vi.fn(),
      clearAttachments: vi.fn(),
      send: vi.fn(),
    },
    thread: () => ({ getState: () => ({ messages: [] as unknown[] }) }),
    threads: { switchToNewThread: vi.fn() },
  };
  return {
    ...actual,
    useAui: () => aui,
    unstable_useSlashCommandAdapter: () => ({ adapter: {}, action: {} }),
    unstable_useMentionAdapter: () => ({ adapter: {}, directive: {} }),
  };
});

vi.mock("@digithings/web/chat/thread", () => ({
  DigichatThread: ({
    onComposerSubmit,
  }: {
    onComposerSubmit?: (event: { preventDefault: () => void }) => void;
  }) => {
    capture.submit = onComposerSubmit ?? null;
    return <div data-testid="digichat-thread" />;
  },
}));

function prefsApi(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS },
    setWebSearch: vi.fn(),
    setDigisearch: vi.fn(),
    setVault: vi.fn(),
    setExtraTool: vi.fn(),
    extraToolOn: (id) => over.prefs?.extra?.[id] !== false,
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
    allowUserMcp: false,
    allowAddMcp: false,
    catalogTools: [],
    mcpServers: [],
    sessionKey: "embed-host",
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

function submitAs(api: EmbedChatPrefsApi, text: string): void {
  render(
    <SkinChromeProvider value={{ ...DEFAULT_SKIN_CHROME, mode: "embed" }}>
      <EmbedChatPrefsProvider value={api}>
        <DigichatSkin />
      </EmbedChatPrefsProvider>
    </SkinChromeProvider>,
  );
  expect(capture.submit).not.toBeNull();
  composerState.text = text;
  capture.submit!({ preventDefault: () => {} });
}

describe("DigichatSkin force-web arm (#3871)", () => {
  it("datatap-shape deny tenant typing /websearch foo emits no pending flag", () => {
    const sessionKey = "deny-tenant-websearch";
    submitAs(
      prefsApi({ tenantAllowsWeb: false, sessionKey, catalogTools: [] }),
      "/websearch foo",
    );
    expect(takePendingWebSearchForce(sessionKey)).toBe(false);
  });

  it("allowed tenant typing /websearch foo still arms this-send web search", () => {
    const sessionKey = "allow-tenant-websearch";
    submitAs(prefsApi({ tenantAllowsWeb: true, sessionKey }), "/websearch foo");
    expect(takePendingWebSearchForce(sessionKey)).toBe(true);
  });
});
