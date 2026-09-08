import { describe, expect, it } from "vitest";
import {
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

  it("waits on empty /search and /vault instead of sending", () => {
    const search = parseSlashInput("/search");
    expect(search).toMatchObject({ kind: "incomplete", prefix: "/search " });
    const vault = parseSlashInput("/vault   ");
    expect(vault).toMatchObject({ kind: "incomplete", prefix: "/vault " });
  });

  it("keeps /docs as a vault alias", () => {
    expect(parseSlashInput("/docs notes")).toMatchObject({
      kind: "command",
      command: { id: "vault", forceTool: "digivault" },
      arg: "notes",
    });
  });

  it("uses the user string as the argument — no model hint", () => {
    const parsed = parseSlashInput("/search RS256 token exchange");
    expect(parsed).toEqual({
      kind: "command",
      command: expect.objectContaining({
        id: "search",
        forceTool: "digisearch",
      }),
      arg: "RS256 token exchange",
    });
    if (parsed.kind !== "command") throw new Error("expected command");
    expect(parsed.arg).not.toMatch(/please/i);
  });

  it("aliases /docs onto vault force, and treats /digisearch /digivault as toggles", () => {
    expect(parseSlashInput("/docs notes")).toMatchObject({
      kind: "command",
      command: { id: "vault", forceTool: "digivault" },
      arg: "notes",
    });
    expect(parseSlashInput("/digisearch")).toMatchObject({
      kind: "command",
      command: { id: "toggle-digisearch", kind: "toggle" },
    });
    expect(parseSlashInput("/digivault")).toMatchObject({
      kind: "command",
      command: { id: "toggle-digivault", kind: "toggle" },
    });
  });

  it("parses client-only /help /new /lang /websearch /settings /byok", () => {
    expect(parseSlashInput("/help")).toMatchObject({ kind: "command", command: { id: "help" } });
    expect(parseSlashInput("/new")).toMatchObject({ kind: "command", command: { id: "new" } });
    expect(parseSlashInput("/websearch")).toMatchObject({
      kind: "command",
      command: { id: "websearch" },
    });
    expect(parseSlashInput("/settings")).toMatchObject({
      kind: "command",
      command: { id: "settings" },
    });
    expect(parseSlashInput("/byok")).toMatchObject({ kind: "command", command: { id: "byok" } });
    expect(parseSlashInput("/key")).toMatchObject({ kind: "command", command: { id: "byok" } });
    expect(parseSlashInput("/lang de")).toMatchObject({
      kind: "command",
      command: { id: "lang" },
      arg: "de",
    });
    expect(parseSlashInput("/language dutch")).toMatchObject({
      kind: "command",
      command: { id: "lang" },
      arg: "dutch",
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

  it("keeps /copy and /export wired as arg-less client commands (#3658)", () => {
    expect(SLASH_COMMANDS.find((c) => c.id === "copy")).toMatchObject({
      names: ["/copy"],
      needsArg: false,
      hint: "Copy last answer as markdown",
      kind: "client",
    });
    expect(SLASH_COMMANDS.find((c) => c.id === "export")).toMatchObject({
      names: ["/export"],
      needsArg: false,
      hint: "Download thread as markdown",
      kind: "client",
    });
  });
});

describe("matchingSlashCommands", () => {
  it("lists public copy for a bare slash including Vault / Web search / BYOK / Settings", () => {
    const matches = matchingSlashCommands("/", { webSearch: true, byok: true });
    const hints = matches.map((c) => c.hint);
    expect(hints).toContain("Search the knowledge base");
    expect(hints).toContain("Vault");
    expect(hints).toContain("Toggle web search");
    expect(hints).toContain("BYOK");
    expect(hints).toContain("Settings");
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
    expect(matchingSlashCommands("/se").map((c) => c.id)).toEqual(["search", "settings"]);
    expect(matchingSlashCommands("/sear").map((c) => c.id)).toEqual(["search"]);
    expect(matchingSlashCommands("/search foo")).toEqual([]);
    expect(matchingSlashCommands("/va").map((c) => c.id)).toEqual(["vault"]);
    expect(matchingSlashCommands("/digis").map((c) => c.id)).toEqual(["toggle-digisearch"]);
  });

  it("lists /copy and /export in the palette and narrows by prefix (#3658)", () => {
    const bare = matchingSlashCommands("/", { webSearch: true, byok: true }).map((c) => c.id);
    expect(bare).toContain("copy");
    expect(bare).toContain("export");
    // Always visible — not gated behind websearch/byok flags.
    expect(matchingSlashCommands("/").map((c) => c.id)).toContain("copy");
    expect(matchingSlashCommands("/").map((c) => c.id)).toContain("export");
    expect(matchingSlashCommands("/cop").map((c) => c.id)).toEqual(["copy"]);
    expect(matchingSlashCommands("/exp").map((c) => c.id)).toEqual(["export"]);
    expect(matchingSlashCommands("/copy foo")).toEqual([]);
  });
});

describe("slashHelpText", () => {
  it("uses public Vault copy, not Docs or raw tool ids", () => {
    const help = slashHelpText({ webSearch: true, byok: true });
    expect(help).toContain("/search — Search the knowledge base");
    expect(help).toContain("/vault — Vault");
    expect(help).toContain("/websearch — Toggle web search");
    expect(help).toContain("/byok — BYOK");
    expect(help).toContain("/settings — Settings");
    expect(help).not.toContain("digivault_get_note");
    expect(help).not.toContain("/docs —");
    expect(help).toContain("/digisearch — Toggle corpus search");
    expect(help).toContain("/digivault — Toggle vault");
  });

  it("lists /copy and /export with client copy (#3658)", () => {
    const help = slashHelpText({ webSearch: true, byok: true });
    expect(help).toContain("/copy — Copy last answer as markdown");
    expect(help).toContain("/export — Download thread as markdown");
    // Not gated behind websearch/byok flags.
    expect(slashHelpText()).toContain("/copy — Copy last answer as markdown");
    expect(slashHelpText()).toContain("/export — Download thread as markdown");
  });
});

describe("isLangCode", () => {
  it("accepts the featured list only", () => {
    expect(isLangCode("nl")).toBe(true);
    expect(isLangCode("de")).toBe(false);
    expect(isLangCode("klingon")).toBe(false);
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
    expect(
      formatCliSettingLine(
        {
          id: "lang",
          label: "Language",
          description: "presets",
          kind: "choice",
          value: "de",
          options: [{ value: "de", label: "German" }],
        },
        false,
      ),
    ).toBe("  Language: German — presets");
  });
});
