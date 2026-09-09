import { describe, expect, it, vi } from "vitest";
import { DEFAULT_EMBED_CHAT_PREFS, type EmbedChatPrefsApi } from "./embed-chat-prefs";
import {
  applySessionTool,
  sessionToolCallsFromMessages,
} from "./session-prefs-tools";

function api(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS, ...over.prefs },
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
    allowAddMcp: false,
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

describe("applySessionTool", () => {
  it("maps language, model, effort, thinking, and tools onto prefs", () => {
    const a = api();
    expect(applySessionTool("session_set_language", { code: "Dutch" }, a).ok).toBe(true);
    expect(a.setLanguage).toHaveBeenCalledWith("nl");
    applySessionTool("session_set_model", { model: "openai/gpt-oss-20b:free" }, a);
    expect(a.setModel).toHaveBeenCalled();
    applySessionTool("session_set_effort", { effort: "high" }, a);
    expect(a.setEffort).toHaveBeenCalledWith("high");
    applySessionTool("session_set_thinking", { enabled: false }, a);
    expect(a.setThinking).toHaveBeenCalledWith(false);
    applySessionTool("session_toggle_tool", { id: "digisearch", enabled: false }, a);
    expect(a.setDigisearch).toHaveBeenCalledWith(false);
  });

  it("opens /mcp after upserting a new URL", () => {
    const a = api();
    const result = applySessionTool(
      "session_upsert_mcp",
      { id: "linear", url: "https://mcp.linear.app/mcp", auth: "oauth" },
      a,
    );
    expect(result.ok).toBe(true);
    expect(a.setMcpConfig).toHaveBeenCalled();
    expect(a.openMcp).toHaveBeenCalledWith("linear");
  });

  it("refuses a new session MCP URL when allowUserMcp is off", () => {
    const a = api({ allowUserMcp: false });
    const result = applySessionTool(
      "session_upsert_mcp",
      { id: "linear", url: "https://mcp.linear.app/mcp", auth: "oauth" },
      a,
    );
    expect(result.ok).toBe(false);
    expect(a.setMcpConfig).not.toHaveBeenCalled();
  });

  it("still attaches a token to an operator id when allowUserMcp is off", () => {
    const a = api({
      allowUserMcp: false,
      mcpServers: [{ id: "datatap", label: "DataTap" }],
    });
    const result = applySessionTool(
      "session_upsert_mcp",
      { id: "datatap", auth: "oauth", token: "tok" },
      a,
    );
    expect(result.ok).toBe(true);
    expect(a.setMcpConfig).toHaveBeenCalled();
    const draft = (a.setMcpConfig as ReturnType<typeof vi.fn>).mock.calls[0]?.[0] as {
      url?: string;
      source?: string;
    };
    expect(draft.source).toBe("operator");
    expect(draft.url).toBe("");
  });
});

describe("sessionToolCallsFromMessages", () => {
  it("reads AI SDK tool-session_* parts", () => {
    const calls = sessionToolCallsFromMessages([
      {
        role: "assistant",
        parts: [
          {
            type: "tool-session_set_language",
            toolCallId: "c1",
            state: "output-available",
            input: { code: "nl" },
          },
        ],
      },
    ]);
    expect(calls).toEqual([{ id: "c1", name: "session_set_language", args: { code: "nl" } }]);
  });
});
