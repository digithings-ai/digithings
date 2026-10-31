import { describe, expect, it, vi } from "vitest";
import { DEFAULT_EMBED_CHAT_PREFS, type EmbedChatPrefsApi } from "@digithings/ui/chat/stock";
import { resolveTenantLanguagePick } from "@/lib/tenant-locales";
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
    setView: vi.fn(),
    setThinking: vi.fn(),
    setModel: vi.fn(),
    setEffort: vi.fn(),
    setSearchEngine: vi.fn(),
    setToolbar: vi.fn(),
    setScrollbars: vi.fn(),
    setDensity: vi.fn(),
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
    newThread: vi.fn(),
    compactThread: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    ...over,
  };
}

describe("applySessionTool", () => {
  it("maps language, model, effort, view, and thinking onto prefs", () => {
    const a = api();
    expect(applySessionTool("session_set_language", { code: "Dutch" }, a).ok).toBe(true);
    expect(a.setLanguage).toHaveBeenCalledWith("nl");
    applySessionTool("session_set_model", { model: "openai/gpt-oss-20b:free" }, a);
    expect(a.setModel).toHaveBeenCalled();
    applySessionTool("session_set_effort", { effort: "high" }, a);
    expect(a.setEffort).toHaveBeenCalledWith("high");
    applySessionTool("session_set_search_engine", { engine: "exa" }, a);
    expect(a.setSearchEngine).toHaveBeenCalledWith("exa");
    expect(applySessionTool("session_set_search_engine", { engine: "bogus" }, a).ok).toBe(
      false,
    );
    applySessionTool("session_set_view", { mode: "balanced" }, a);
    expect(a.setView).toHaveBeenCalledWith("balanced");
    // Boolean-era contract still maps onto the 3-mode thinking pref.
    applySessionTool("session_set_thinking", { enabled: false }, a);
    expect(a.setThinking).toHaveBeenCalledWith("collapsed");
    applySessionTool("session_set_thinking", { mode: "open" }, a);
    expect(a.setThinking).toHaveBeenCalledWith("open");
  });

  it("refuses session_toggle_tool on an unlocked host and points at /tools", () => {
    const unlocked = api();
    const result = applySessionTool(
      "session_toggle_tool",
      { id: "digisearch", enabled: false },
      unlocked,
    );
    expect(result).toEqual({ ok: false, message: "Tools are changed in /tools." });
    expect(unlocked.setDigisearch).not.toHaveBeenCalled();
    expect(unlocked.setVault).not.toHaveBeenCalled();
    expect(unlocked.setWebSearch).not.toHaveBeenCalled();
    expect(unlocked.setExtraTool).not.toHaveBeenCalled();

    const toggle = api({ toolControl: "toggle" });
    const toggleResult = applySessionTool(
      "session_toggle_tool",
      { id: "websearch", enabled: true },
      toggle,
    );
    expect(toggleResult.ok).toBe(false);
    expect(toggleResult.message).toBe("Tools are changed in /tools.");
    expect(toggle.setWebSearch).not.toHaveBeenCalled();
  });

  it("does not toggle tools when the host locks them or the agent owns them", () => {
    const locked = api({ toolControl: "locked" });
    const lockedResult = applySessionTool(
      "session_toggle_tool",
      { id: "digisearch", enabled: false },
      locked,
    );
    expect(lockedResult.ok).toBe(false);
    expect(lockedResult.message).toBe("Tools are locked for this host.");
    expect(locked.setDigisearch).not.toHaveBeenCalled();

    const agent = api({ toolControl: "agent" });
    const agentResult = applySessionTool(
      "session_toggle_tool",
      { id: "file_search", enabled: true },
      agent,
    );
    expect(agentResult.ok).toBe(false);
    expect(agentResult.message).toBe("Tools are locked for this host.");
    expect(agent.setExtraTool).not.toHaveBeenCalled();
  });

  it("names only the live view levels when a view is refused", () => {
    // The model-facing message teaches the levels the product ships; retired
    // ids (`compact` etc.) fold forward like `/view` does.
    const a = api();
    expect(applySessionTool("session_set_view", { mode: "compact" }, a).ok).toBe(true);
    expect(a.setView).toHaveBeenCalledWith("quiet");
    (a.setView as ReturnType<typeof vi.fn>).mockClear();
    const result = applySessionTool("session_set_view", { mode: "loud" }, a);
    expect(result.ok).toBe(false);
    expect(result.message).toBe("View must be quiet, balanced, or verbose.");
    expect(a.setView).not.toHaveBeenCalled();
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
    expect(calls).toEqual([
      {
        id: "0:c1",
        name: "session_set_language",
        args: { code: "nl" },
        done: true,
        refused: false,
        prefs: null,
      },
    ]);
  });
});

describe("session_set_language and the tenant language list", () => {
  /** An api whose setLanguage enforces the list the way the embed does. */
  function tenantApi(allowed: readonly string[] | undefined) {
    const picked: string[] = [];
    const a = api({
      ...(allowed ? { allowedLanguages: allowed } : {}),
      setLanguage: vi.fn((code: string) => {
        const next = resolveTenantLanguagePick(allowed, code);
        if (next) picked.push(next);
      }),
    });
    return { a, picked };
  }

  it("switches to a language the tenant offers", () => {
    const { a, picked } = tenantApi(["en", "fr"]);
    const out = applySessionTool("session_set_language", { code: "French" }, a);
    expect(out).toEqual({ ok: true, message: "Language set to fr." });
    expect(picked).toEqual(["fr"]);
  });

  it("refuses a language the tenant does not offer and changes nothing", () => {
    const { a, picked } = tenantApi(["en", "fr"]);
    const out = applySessionTool("session_set_language", { code: "Dutch" }, a);
    expect(out.ok).toBe(false);
    expect(out.message).toBe("This chat only answers in en, fr; the language was not changed.");
    expect(a.setLanguage).not.toHaveBeenCalled();
    expect(picked).toEqual([]);
  });

  it("is unchanged when the tenant sets no list", () => {
    const { a, picked } = tenantApi(undefined);
    expect(applySessionTool("session_set_language", { code: "Dutch" }, a).ok).toBe(true);
    expect(picked).toEqual(["nl"]);
  });

  it("pins a single-language tenant to its language", () => {
    const { a, picked } = tenantApi(["fr"]);
    expect(applySessionTool("session_set_language", { code: "en" }, a).ok).toBe(false);
    expect(applySessionTool("session_set_language", { code: "fr" }, a).ok).toBe(true);
    expect(picked).toEqual(["fr"]);
  });
});

describe("session tools apply live state (stub model run)", () => {
  /** One assistant turn the way the BFF streams it: `{...input, result}`. */
  function turn(id: string, calls: { name: string; args: Record<string, unknown>; result: unknown; isError?: boolean }[]) {
    return {
      id,
      role: "assistant",
      status: { type: "complete" },
      content: calls.map((c, i) => ({
        type: "tool-call",
        toolName: c.name,
        // The stream numbers calls per turn, so ids repeat across turns.
        toolCallId: `tool-${i + 1}`,
        args: c.args,
        result: { ...c.args, result: c.result },
        isError: c.isError === true,
      })),
    };
  }

  function drive(messages: unknown[], prefsApi: EmbedChatPrefsApi) {
    for (const call of sessionToolCallsFromMessages(messages)) {
      if (!call.done || call.refused) continue;
      applySessionTool(call.name, { ...call.args, ...(call.prefs ?? {}) }, prefsApi);
    }
  }

  it("applies model, theme, density, language and view from the server result", () => {
    const setTheme = vi.fn();
    const a = api({
      availableModels: ["acme/fast-1", "acme/deep-2"],
      allowedLanguages: ["en", "fr"],
      setTheme,
      themeState: { preference: "light", palette: "default", resolved: "light" },
    } as Partial<EmbedChatPrefsApi>);
    drive(
      [
        turn("m1", [{ name: "session_set_model", args: { model: "deep" }, result: { ok: true, session_prefs: { model: "deep" } } }]),
        turn("m2", [
          { name: "session_set_theme", args: { mode: "dark", palette: "nord" }, result: { ok: true, session_prefs: { mode: "dark", palette: "nord" } } },
          { name: "session_set_density", args: { density: "airy" }, result: { ok: true, session_prefs: { density: "airy" } } },
          { name: "session_set_language", args: { code: "French" }, result: { ok: true, session_prefs: { code: "fr" } } },
          { name: "session_set_view", args: { mode: "detailed" }, result: { ok: true, session_prefs: { mode: "verbose" } } },
        ]),
      ],
      a,
    );
    expect(a.setModel).toHaveBeenCalledWith("acme/deep-2");
    expect(setTheme).toHaveBeenCalledWith("dark", "nord");
    expect(a.setDensity).toHaveBeenCalledWith("airy");
    expect(a.setLanguage).toHaveBeenCalledWith("fr");
    expect(a.setView).toHaveBeenCalledWith("verbose");
  });

  it("scopes call ids by message so a later turn's tool-1 still applies", () => {
    const hits = sessionToolCallsFromMessages([
      turn("m1", [{ name: "session_set_density", args: { density: "airy" }, result: { ok: true } }]),
      turn("m2", [{ name: "session_set_density", args: { density: "compact" }, result: { ok: true } }]),
    ]);
    expect(new Set(hits.map((h) => h.id)).size).toBe(2);
  });

  it("does not apply a refused call (ok:false) or an errored one", () => {
    const a = api();
    drive(
      [
        turn("m1", [
          { name: "session_set_language", args: { code: "de" }, result: { ok: false, error: "not offered" } },
          { name: "session_set_density", args: { density: "airy" }, result: { error: "boom" }, isError: true },
        ]),
      ],
      a,
    );
    expect(a.setLanguage).not.toHaveBeenCalled();
    expect(a.setDensity).not.toHaveBeenCalled();
  });

  it("waits for the result before applying", () => {
    const [hit] = sessionToolCallsFromMessages([
      { id: "m1", role: "assistant", content: [{ type: "tool-call", toolName: "session_set_density", toolCallId: "tool-1", args: { density: "airy" } }] },
    ]);
    expect(hit.done).toBe(false);
  });

  it("refuses a model the chat does not offer, with the list", () => {
    const a = api({ availableModels: ["acme/fast-1"] } as Partial<EmbedChatPrefsApi>);
    const out = applySessionTool("session_set_model", { model: "other/x" }, a);
    expect(out.ok).toBe(false);
    expect(out.message).toContain("acme/fast-1");
    expect(a.setModel).not.toHaveBeenCalled();
  });

  it("theme is refused when the host locks it and validates mode/palette", () => {
    expect(applySessionTool("session_set_theme", { mode: "dark" }, api({ themeLocked: true } as Partial<EmbedChatPrefsApi>)).ok).toBe(false);
    expect(applySessionTool("session_set_theme", { mode: "neon" }, api()).ok).toBe(false);
    expect(applySessionTool("session_set_theme", { palette: "nope" }, api()).ok).toBe(false);
  });

  it("density rejects unknown values", () => {
    const a = api();
    expect(applySessionTool("session_set_density", { density: "huge" }, a).ok).toBe(false);
    expect(a.setDensity).not.toHaveBeenCalled();
  });
});
