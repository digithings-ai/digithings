import { describe, expect, it, vi } from "vitest";
import { parseSlashInput, slashHelpText } from "@digithings/digichat-ui";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  type EmbedChatPrefsApi,
} from "@/components/stock/embed-chat-prefs";
import {
  buildProductSlashCommands,
  catalogForceTool,
  executeSlashDef,
  extraSlashDefs,
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
    sessionKey: "embed-host",
    openSettings: vi.fn(),
    openMcp: vi.fn(),
    openByok: vi.fn(),
    openModels: vi.fn(),
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
  it("includes catalog tools, mcp, models, and featured languages", () => {
    const cmds = buildProductSlashCommands(api());
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
  });

  it("hides websearch when the tenant disallows it", () => {
    const ids = buildProductSlashCommands(api({ tenantAllowsWeb: false })).map((c) => c.id);
    expect(ids).not.toContain("websearch");
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

describe("executeSlashDef", () => {
  it("resets prefs and starts a new thread on /new", () => {
    const a = api();
    const def = { id: "new" as const, names: ["/new"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.reset).toHaveBeenCalledOnce();
    expect(a.newThread).toHaveBeenCalledOnce();
  });

  it("does not toggle tools on /help (skin inserts the help text)", () => {
    const a = api();
    const def = { id: "help" as const, names: ["/help"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openSettings).not.toHaveBeenCalled();
    expect(a.setDigisearch).not.toHaveBeenCalled();
  });

  it("opens the MCP pane on /mcp", () => {
    const a = api();
    const def = { id: "mcp" as const, names: ["/mcp"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openMcp).toHaveBeenCalledOnce();
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
