import { describe, expect, it, vi } from "vitest";
import { parseSlashInput, slashHelpText } from "@digithings/digichat-ui";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  type EmbedChatPrefsApi,
} from "@/components/stock/embed-chat-prefs";
import { emptyMcpConfig } from "@/components/stock/embed-mcp-flow";
import {
  buildProductSlashCommands,
  catalogForceTool,
  executeSlashDef,
  extraSlashDefs,
  prefixSlashAdapter,
  slashItemPrefixMatch,
  slashSubmitAction,
} from "./product-slash-commands";

function api(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
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
    catalogTools: [
      { id: "digisearch", label: "Search" },
      { id: "digivault", label: "Vault" },
      { id: "web_search", label: "Web search" },
    ],
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

describe("slashSubmitAction", () => {
  it("forces /digisearch and /digivault with the remainder as the user message", () => {
    expect(slashSubmitAction("/digisearch RS256")).toEqual({
      kind: "force",
      forceTool: "digisearch",
      text: "RS256",
    });
    expect(slashSubmitAction("/digivault notes")).toEqual({
      kind: "force",
      forceTool: "digivault",
      text: "notes",
    });
  });

  it("runs empty /digisearch as a session toggle", () => {
    expect(slashSubmitAction("/digisearch")).toMatchObject({
      kind: "run",
      command: { id: "digisearch" },
      arg: "",
    });
  });

  it("forces /websearch query as this-send web search", () => {
    expect(slashSubmitAction("/websearch latest filings")).toEqual({
      kind: "force-web",
      text: "latest filings",
    });
  });

  it("forces extra MCP catalog ids", () => {
    const extra = extraSlashDefs(
      api({ catalogTools: [{ id: "datatap", label: "DataTap" }] }),
    );
    expect(slashSubmitAction("/datatap pipeline status", extra)).toEqual({
      kind: "force",
      forceTool: "datatap",
      text: "pipeline status",
    });
    expect(slashSubmitAction("/datatap", extra)).toMatchObject({
      kind: "run",
      command: { id: "datatap" },
      arg: "",
    });
  });

  it("runs /language dutch as a client command", () => {
    expect(slashSubmitAction("/language dutch")).toMatchObject({
      kind: "run",
      command: { id: "lang" },
      arg: "dutch",
    });
    expect(slashSubmitAction("/language en")).toMatchObject({
      kind: "run",
      command: { id: "lang" },
      arg: "en",
    });
    expect(slashSubmitAction("/language Italiano")).toMatchObject({
      kind: "run",
      command: { id: "lang" },
      arg: "Italiano",
    });
  });

  it("passes ordinary text through", () => {
    expect(slashSubmitAction("how does auth work")).toEqual({ kind: "pass" });
  });

  it("blocks unknown slash lines instead of sending them", () => {
    expect(slashSubmitAction("/not-a-command")).toEqual({ kind: "block" });
  });

  it("does not treat a slashHelpText dump as /digisearch", () => {
    const help = slashHelpText({
      webSearch: true,
      byok: true,
      digisearch: true,
      digivault: true,
    });
    expect(help.startsWith("/digisearch")).toBe(true);
    expect(slashSubmitAction(help)).toEqual({ kind: "block" });
  });
});

describe("catalogForceTool", () => {
  it("maps vault locate onto the BFF catalog id", () => {
    expect(catalogForceTool("digivault_search_notes")).toBe("digivault");
    expect(catalogForceTool("digisearch")).toBe("digisearch");
    expect(catalogForceTool("datatap")).toBe("datatap");
  });
});

describe("buildProductSlashCommands", () => {
  it("includes catalog tools, mcp, models, and featured languages without per-row icons", () => {
    const cmds = buildProductSlashCommands(api({ allowUserMcp: true }));
    const ids = cmds.map((c) => c.id);
    expect(ids).toContain("websearch");
    expect(ids).toContain("digisearch");
    expect(ids).toContain("digivault");
    expect(ids).toContain("mcp");
    expect(ids).toContain("models");
    expect(ids).toContain("dutch");
    expect(ids).toContain("language");
    expect(ids).not.toContain("search");
    expect(ids).not.toContain("toggle-digisearch");
    expect(cmds.every((c) => !("icon" in c) || c.icon == null)).toBe(true);
  });

  it("hides catalog/MCP commands when the install has no tools", () => {
    const ids = buildProductSlashCommands(
      api({
        tenantAllowsWeb: false,
        showByok: false,
        showModels: false,
        hasDigisearch: false,
        hasVault: false,
        allowUserMcp: false,
        catalogTools: [],
        mcpServers: [],
      }),
    ).map((c) => c.id);
    expect(ids).not.toContain("digisearch");
    expect(ids).not.toContain("digivault");
    expect(ids).not.toContain("websearch");
    expect(ids).not.toContain("mcp");
    expect(ids).not.toContain("tools");
    expect(ids).not.toContain("models");
    expect(ids).toContain("language");
    expect(ids).toContain("thinking");
  });

  it("adds extra MCP catalog commands", () => {
    const ids = buildProductSlashCommands(
      api({ catalogTools: [{ id: "datatap", label: "DataTap" }] }),
    ).map((c) => c.id);
    expect(ids).toContain("datatap");
  });

  it("still parses /digisearch as a tool command", () => {
    expect(parseSlashInput("/digisearch")).toMatchObject({
      kind: "command",
      command: { id: "digisearch", kind: "tool" },
    });
  });
});

describe("slashItemPrefixMatch", () => {
  it("does not treat /se as a match for /digisearch", () => {
    expect(slashItemPrefixMatch({ id: "digisearch", label: "/digisearch" }, "search")).toBe(
      false,
    );
    expect(
      slashItemPrefixMatch({ id: "digisearch", label: "/digisearch" }, "digi"),
    ).toBe(true);
  });
});

describe("prefixSlashAdapter", () => {
  it("filters the inner search with prefix match and does not add categories", () => {
    const inner = {
      categories: () => [{ id: "tools", label: "Tools" }],
      search: (_query: string) => [
        { id: "settings", label: "/settings" },
        { id: "digisearch", label: "/digisearch" },
      ],
    };
    const wrapped = prefixSlashAdapter(inner);
    expect(wrapped.search("se").map((i) => i.id)).toEqual(["settings"]);
    expect(wrapped.categories()).toEqual([]);
  });
});

describe("executeSlashDef", () => {
  it("resets prefs and starts a new thread on /new", () => {
    const a = api();
    const def = { id: "new" as const, names: ["/new"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.reset).toHaveBeenCalledOnce();
    expect(a.newThread).toHaveBeenCalledOnce();
  });

  it("does not toggle tools on /help (palette is the help; do not dump into the composer)", () => {
    const a = api();
    const def = { id: "help" as const, names: ["/help"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openSettings).not.toHaveBeenCalled();
    expect(a.setDigisearch).not.toHaveBeenCalled();
  });

  it("opens the language list on empty /language and sets from code, English, or autonym", () => {
    const a = api();
    const def = { id: "lang" as const, names: ["/language", "/lang"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openLanguage).toHaveBeenCalledOnce();
    executeSlashDef(def, "en", a);
    expect(a.setLanguage).toHaveBeenCalledWith("en");
    executeSlashDef(def, "Italiano", a);
    expect(a.setLanguage).toHaveBeenCalledWith("it");
    executeSlashDef(def, "espanol", a);
    expect(a.setLanguage).toHaveBeenCalledWith("es");
  });

  it("opens /provider and seeds a provider from the remainder", () => {
    const a = api();
    const def = { id: "byok" as const, names: ["/provider", "/byok", "/key"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openByok).toHaveBeenCalledWith("");
    executeSlashDef(def, "openai", a);
    expect(a.openByok).toHaveBeenCalledWith("openai");
  });

  it("opens the MCP server menu on /mcp and seeds /mcp new", () => {
    const a = api();
    const def = { id: "mcp" as const, names: ["/mcp"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openMcp).toHaveBeenCalledWith("");
    executeSlashDef(def, "new", a);
    expect(a.openMcp).toHaveBeenCalledWith("new");
  });

  it("opens the connected-tools menu on /tools", () => {
    const a = api();
    const def = { id: "tools" as const, names: ["/tools"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openTools).toHaveBeenCalledOnce();
  });

  it("exposes extra MCP servers as slash tools", () => {
    const extra = extraSlashDefs(
      api({
        catalogTools: [{ id: "digisearch" }],
        mcpServers: [{ id: "datatap", label: "DataTap" }],
      }),
    );
    expect(extra.map((d) => d.names[0])).toEqual(["/datatap"]);
    expect(slashSubmitAction("/datatap pipeline", extra)).toEqual({
      kind: "force",
      forceTool: "datatap",
      text: "pipeline",
    });
  });

  it("exposes session MCP configs as slash tools", () => {
    const extra = extraSlashDefs(
      api({
        catalogTools: [],
        mcpServers: [],
        prefs: {
          ...DEFAULT_EMBED_CHAT_PREFS,
          mcpCustom: [{ ...emptyMcpConfig(), id: "linear", label: "Linear" }],
        },
      }),
    );
    expect(extra.map((d) => d.names[0])).toEqual(["/linear"]);
  });

  it("toggles extra MCP tools", () => {
    const a = api({
      extraToolOn: () => true,
      catalogTools: [{ id: "datatap" }],
    });
    executeSlashDef(
      { id: "datatap", names: ["/datatap"], needsArg: false, hint: "", kind: "tool" },
      "",
      a,
    );
    expect(a.setExtraTool).toHaveBeenCalledWith("datatap", false);
  });
});
