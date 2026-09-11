import { describe, expect, it } from "vitest";
import {
  catalogToolSlashDef,
  formatCliSettingLine,
  isLangCode,
  LANG_LABELS,
  matchingSlashCommands,
  nextPaletteIndex,
  parseSlashInput,
  SLASH_COMMANDS,
  slashHelpText,
} from "./slash-commands";

describe("parseSlashInput", () => {
  it("treats ordinary text as none", () => {
    expect(parseSlashInput("how does auth work")).toEqual({ kind: "none" });
  });

  it("treats empty /digisearch as a toggle, not incomplete", () => {
    expect(parseSlashInput("/digisearch")).toMatchObject({
      kind: "command",
      command: { id: "digisearch", kind: "tool" },
      arg: "",
    });
  });

  it("drops /search /vault /docs as public names", () => {
    expect(parseSlashInput("/search RS256")).toEqual({ kind: "unknown", name: "/search" });
    expect(parseSlashInput("/vault notes")).toEqual({ kind: "unknown", name: "/vault" });
    expect(parseSlashInput("/docs notes")).toEqual({ kind: "unknown", name: "/docs" });
  });

  it("uses the remainder after /digisearch as the force query", () => {
    const parsed = parseSlashInput("/digisearch RS256 token exchange");
    expect(parsed).toEqual({
      kind: "command",
      command: expect.objectContaining({
        id: "digisearch",
        forceTool: "digisearch",
        kind: "tool",
      }),
      arg: "RS256 token exchange",
    });
  });

  it("aliases /clear onto a new-conversation command", () => {
    expect(parseSlashInput("/clear")).toMatchObject({
      kind: "command",
      command: { id: "clear" },
    });
  });

  it("parses client-only /help /new /lang /websearch /settings /provider /mcp", () => {
    expect(parseSlashInput("/help")).toMatchObject({ kind: "command", command: { id: "help" } });
    expect(parseSlashInput("/new")).toMatchObject({ kind: "command", command: { id: "new" } });
    expect(parseSlashInput("/websearch")).toMatchObject({
      kind: "command",
      command: { id: "websearch", kind: "tool" },
    });
    expect(parseSlashInput("/settings")).toMatchObject({
      kind: "command",
      command: { id: "settings" },
    });
    expect(parseSlashInput("/provider")).toMatchObject({ kind: "command", command: { id: "byok" } });
    expect(parseSlashInput("/byok")).toMatchObject({ kind: "command", command: { id: "byok" } });
    expect(parseSlashInput("/key")).toMatchObject({ kind: "command", command: { id: "byok" } });
    expect(parseSlashInput("/provider openai")).toMatchObject({
      kind: "command",
      command: { id: "byok" },
      arg: "openai",
    });
    expect(parseSlashInput("/mcp")).toMatchObject({ kind: "command", command: { id: "mcp" } });
    expect(parseSlashInput("/mcp new")).toMatchObject({
      kind: "command",
      command: { id: "mcp" },
      arg: "new",
    });
    expect(parseSlashInput("/tools")).toMatchObject({ kind: "command", command: { id: "tools" } });
    expect(parseSlashInput("/models")).toMatchObject({ kind: "command", command: { id: "models" } });
    expect(parseSlashInput("/lang de")).toMatchObject({
      kind: "command",
      command: { id: "lang" },
      arg: "de",
    });
    expect(parseSlashInput("/language Italiano")).toMatchObject({
      kind: "command",
      command: { id: "lang" },
      arg: "Italiano",
    });
    expect(parseSlashInput("/effort")).toMatchObject({
      kind: "command",
      command: { id: "effort" },
    });
  });

  it("parses extra catalog MCP tools", () => {
    const extra = [catalogToolSlashDef({ id: "datatap", label: "DataTap" })];
    expect(parseSlashInput("/datatap", extra)).toMatchObject({
      kind: "command",
      command: { id: "datatap", kind: "tool" },
      arg: "",
    });
    expect(parseSlashInput("/datatap pipeline status", extra)).toMatchObject({
      kind: "command",
      arg: "pipeline status",
    });
  });

  it("flags unknown commands", () => {
    expect(parseSlashInput("/web")).toEqual({ kind: "unknown", name: "/web" });
  });

  it("parses /copy and /export as client commands (#3658)", () => {
    expect(parseSlashInput("/copy")).toMatchObject({
      kind: "command",
      command: { id: "copy", kind: "client" },
      arg: "",
    });
    expect(parseSlashInput("/export")).toMatchObject({
      kind: "command",
      command: { id: "export", kind: "client" },
      arg: "",
    });
  });
});

describe("matchingSlashCommands", () => {
  it("lists public copy for a bare slash including tools and settings", () => {
    const matches = matchingSlashCommands("/", { webSearch: true, byok: true });
    const ids = matches.map((c) => c.id);
    expect(ids).toContain("digisearch");
    expect(ids).toContain("digivault");
    expect(ids).toContain("websearch");
    expect(ids).toContain("byok");
    expect(ids).toContain("settings");
    expect(ids).toContain("mcp");
    expect(ids).toContain("tools");
    expect(ids).not.toContain("sessions");
  });

  it("hides websearch unless the tenant allows it", () => {
    expect(matchingSlashCommands("/", { webSearch: false }).map((c) => c.id)).not.toContain(
      "websearch",
    );
    expect(matchingSlashCommands("/", { webSearch: true }).map((c) => c.id)).toContain(
      "websearch",
    );
  });

  it("narrows as the user types a prefix", () => {
    expect(matchingSlashCommands("/se").map((c) => c.id)).toEqual(["settings"]);
    expect(matchingSlashCommands("/sett").map((c) => c.id)).toEqual(["settings"]);
    expect(matchingSlashCommands("/digis").map((c) => c.id)).toEqual(["digisearch"]);
  });

  it("shows /sessions only when visibility.sessions is on", () => {
    expect(matchingSlashCommands("/", { sessions: true }).map((c) => c.id)).toContain("sessions");
    expect(matchingSlashCommands("/").map((c) => c.id)).not.toContain("sessions");
  });
});

describe("slashHelpText", () => {
  it("uses public tool names, not /search or /docs", () => {
    const help = slashHelpText({ webSearch: true, byok: true });
    expect(help).toContain("/digisearch —");
    expect(help).toContain("/digivault —");
    expect(help).toContain("/websearch —");
    expect(help).toContain("/provider — API provider");
    expect(help).toContain("/settings — Settings");
    expect(help).toContain("/mcp — MCP JSON / auth / new");
    expect(help).toContain("/tools — Connected tools");
    expect(help).not.toContain("digivault_get_note");
    expect(help).not.toContain("/search —");
    expect(help).not.toContain("/docs —");
  });
});

describe("isLangCode", () => {
  it("accepts the featured list only", () => {
    expect(isLangCode("nl")).toBe(true);
    expect(isLangCode("de")).toBe(false);
  });
});

describe("LANG_LABELS", () => {
  it("names every featured code in English", () => {
    expect(LANG_LABELS.nl).toBe("Dutch");
    expect(LANG_LABELS.en).toBe("English");
  });
});

describe("nextPaletteIndex", () => {
  it("wraps Up/Down through the palette (#3556)", () => {
    expect(nextPaletteIndex(0, 1, 3)).toBe(1);
    expect(nextPaletteIndex(2, 1, 3)).toBe(0);
    expect(nextPaletteIndex(0, -1, 3)).toBe(2);
    expect(nextPaletteIndex(0, 1, 0)).toBe(0);
  });
});

describe("formatCliSettingLine", () => {
  it("renders toggle and choice rows for the settings panel", () => {
    expect(
      formatCliSettingLine(
        {
          id: "websearch",
          label: "Web search",
          description: "External cites",
          kind: "toggle",
          value: true,
        },
        true,
      ),
    ).toBe("> [on] Web search — External cites");
  });
});

describe("SLASH_COMMANDS", () => {
  it("keeps /copy and /export as arg-less client commands", () => {
    expect(SLASH_COMMANDS.find((c) => c.id === "copy")).toMatchObject({
      names: ["/copy"],
      needsArg: false,
      kind: "client",
    });
  });

  it("lists /provider as the public BYOK name, with /byok and /key as aliases", () => {
    expect(SLASH_COMMANDS.find((c) => c.id === "byok")).toMatchObject({
      names: ["/provider", "/byok", "/key"],
      hint: "API provider",
    });
  });
});
