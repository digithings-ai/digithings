/**
 * The embed chat-prefs test host.
 *
 * It lives outside the test files on purpose: `apps/digichat` excludes
 * `*.test.ts(x)` from its TypeScript program, so a fake that lives in a test
 * file is never type-checked and every test file grows its own copy of it.
 * Here the shape is type-checked and there is one copy of it (#4667).
 *
 * The functions are plain no-ops. A test that asserts on a call replaces the
 * one it needs with a spy (`spyFixture` does that for the whole host).
 */
import {
  DEFAULT_EMBED_CHAT_PREFS,
  type EmbedChatPrefsApi,
} from "@digithings/ui/chat/stock";

export function prefsFixture(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS },
    setWebSearch: () => {},
    setDigisearch: () => {},
    setVault: () => {},
    setExtraTool: () => {},
    extraToolOn: () => true,
    setMcpConfig: () => {},
    removeMcpConfig: () => {},
    setLanguage: () => {},
    setView: () => {},
    setThinking: () => {},
    setModel: () => {},
    setEffort: () => {},
    setSearchEngine: () => {},
    setToolbar: () => {},
    setScrollbars: () => {},
    setDensity: () => {},
    reset: () => {},
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
    openSettings: () => {},
    openHelp: () => {},
    openTools: () => {},
    openMcp: () => {},
    openByok: () => {},
    openModels: () => {},
    openEffort: () => {},
    openSearchEngine: () => {},
    openView: () => {},
    openDensity: () => {},
    openThinking: () => {},
    openLanguage: () => {},
    openSessions: () => {},
    openArtifacts: () => {},
    openTheme: () => {},
    newThread: () => {},
    /** The host can start a conversation and can regenerate the last answer. */
    hasNewThread: true,
    hasRedo: true,
    redo: () => {},
    setComposerDraft: () => {},
    composerDraftBound: true,
    ...over,
  };
}

/**
 * The same host with every function replaced by a spy.
 *
 * The spy factory is passed in, so this module never imports the test
 * runner: a test hands it `vi.fn`. The overrides are applied last, so a test
 * that passes its own mock keeps that exact mock.
 */
export function spyFixture(
  spy: (impl: (...args: never[]) => unknown) => unknown,
  over: Partial<EmbedChatPrefsApi> = {},
): EmbedChatPrefsApi {
  const base = prefsFixture();
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(base)) {
    out[key] = typeof value === "function" ? spy(value as (...args: never[]) => unknown) : value;
  }
  return { ...out, ...over } as EmbedChatPrefsApi;
}
