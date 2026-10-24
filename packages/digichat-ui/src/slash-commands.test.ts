import { describe, expect, it } from "vitest";
import {
  applyPaletteFrame,
  formatCliSettingLine,
  isLangCode,
  LANG_LABELS,
  matchingSlashCommands,
  nextPaletteIndex,
  optionDraft,
  paletteFrame,
  paletteSurfaces,
  paneDraftForId,
  parseSlashInput,
  SLASH_COMMANDS,
  slashHelpText,
  submenuRows,
  VIEW_CHOICES,
  VIEW_CODES,
  VIEW_LABELS,
} from "./slash-commands";

describe("parseSlashInput", () => {
  it("treats ordinary text as none", () => {
    expect(parseSlashInput("how does auth work")).toEqual({ kind: "none" });
  });

  it("does not treat /digisearch as a palette command", () => {
    expect(parseSlashInput("/digisearch")).toEqual({ kind: "unknown", name: "/digisearch" });
    expect(parseSlashInput("/digivault notes")).toEqual({ kind: "unknown", name: "/digivault" });
    expect(parseSlashInput("/websearch query")).toEqual({ kind: "unknown", name: "/websearch" });
    expect(parseSlashInput("/ledger")).toEqual({ kind: "unknown", name: "/ledger" });
  });

  it("drops /search /vault /docs as public names", () => {
    expect(parseSlashInput("/search RS256")).toEqual({ kind: "unknown", name: "/search" });
    expect(parseSlashInput("/vault notes")).toEqual({ kind: "unknown", name: "/vault" });
    expect(parseSlashInput("/docs notes")).toEqual({ kind: "unknown", name: "/docs" });
  });

  it("aliases /clear onto a new-conversation command", () => {
    expect(parseSlashInput("/clear")).toMatchObject({
      kind: "command",
      command: { id: "clear" },
    });
  });

  it("parses client-only /help /new /lang /settings /provider /mcp", () => {
    expect(parseSlashInput("/help")).toMatchObject({ kind: "command", command: { id: "help" } });
    expect(parseSlashInput("/new")).toMatchObject({ kind: "command", command: { id: "new" } });
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
    expect(parseSlashInput("/export html")).toMatchObject({
      kind: "command",
      command: { id: "export", kind: "client" },
      arg: "html",
    });
    expect(parseSlashInput("/export md")).toMatchObject({
      kind: "command",
      command: { id: "export", kind: "client" },
      arg: "md",
    });
  });
});

describe("parseSlashInput edge cases", () => {
  it("treats empty and whitespace-only input as none", () => {
    expect(parseSlashInput("")).toEqual({ kind: "none" });
    expect(parseSlashInput("   ")).toEqual({ kind: "none" });
    expect(parseSlashInput("\n\t ")).toEqual({ kind: "none" });
  });

  it("matches the command token case-insensitively but keeps the argument's case", () => {
    expect(parseSlashInput("/LANGUAGE English")).toMatchObject({
      kind: "command",
      command: { id: "lang" },
      arg: "English",
    });
    expect(parseSlashInput("/HeLp")).toMatchObject({ kind: "command", command: { id: "help" } });
  });

  it("matches an extra definition whatever the casing of its name", () => {
    // paletteFrame() lowercases both sides; parseSlashInput must agree, or a
    // host-supplied `/DigiSearch` is reachable from one surface and not the other.
    const extra = [{ id: "digisearch", names: ["/DigiSearch"], needsArg: false, hint: "Search" }];
    expect(parseSlashInput("/digisearch", extra)).toMatchObject({
      kind: "command",
      command: { id: "digisearch" },
    });
    expect(parseSlashInput("/DIGISEARCH now", extra)).toMatchObject({
      kind: "command",
      command: { id: "digisearch" },
      arg: "now",
    });
  });

  it("collapses runs of whitespace between command and argument", () => {
    expect(parseSlashInput("  /export \t html  ")).toMatchObject({
      kind: "command",
      command: { id: "export" },
      arg: "html",
    });
  });
});

describe("matchingSlashCommands", () => {
  it("lists public copy for a bare slash including tools and settings", () => {
    const matches = matchingSlashCommands("/", { webSearch: true, byok: true });
    const ids = matches.map((c) => c.id);
    expect(ids).not.toContain("digisearch");
    expect(ids).not.toContain("digivault");
    expect(ids).not.toContain("websearch");
    expect(ids).toContain("byok");
    expect(ids).toContain("settings");
    expect(ids).toContain("mcp");
    expect(ids).toContain("tools");
    expect(ids).not.toContain("sessions");
  });

  it("hides search-engine unless the tenant allows web search", () => {
    expect(matchingSlashCommands("/se", { webSearch: false }).map((c) => c.id)).toEqual([
      "settings",
    ]);
    expect(matchingSlashCommands("/se", { webSearch: true }).map((c) => c.id)).toEqual([
      "search-engine",
      "settings",
    ]);
  });

  it("narrows as the user types a prefix", () => {
    expect(matchingSlashCommands("/se").map((c) => c.id)).toEqual(["settings"]);
    expect(matchingSlashCommands("/sett").map((c) => c.id)).toEqual(["settings"]);
    expect(matchingSlashCommands("/digis").map((c) => c.id)).toEqual([]);
    expect(matchingSlashCommands("/tools").map((c) => c.id)).toEqual(["tools"]);
  });

  it("does not keep the palette open on a longer unknown command", () => {
    // `q.startsWith(name)` used to match a row the user had already typed past,
    // so a typo such as /mcpx still showed /mcp as if it were a prefix.
    expect(matchingSlashCommands("/mcpx").map((c) => c.id)).toEqual([]);
    expect(matchingSlashCommands("/toolsx").map((c) => c.id)).toEqual([]);
    expect(matchingSlashCommands("/settingsx").map((c) => c.id)).toEqual([]);
  });

  it("matches a mixed-case prefix", () => {
    expect(matchingSlashCommands("/SETT").map((c) => c.id)).toEqual(["settings"]);
  });

  it("hides /theme when the embed pins the theme", () => {
    expect(matchingSlashCommands("/", { theme: false }).map((c) => c.id)).not.toContain("theme");
    expect(matchingSlashCommands("/theme").map((c) => c.id)).toContain("theme");
  });

  it("shows /sessions only when visibility.sessions is on", () => {
    expect(matchingSlashCommands("/", { sessions: true }).map((c) => c.id)).toContain("sessions");
    expect(matchingSlashCommands("/").map((c) => c.id)).not.toContain("sessions");
  });
});

describe("slashHelpText", () => {
  it("uses public tool names, not /search or /docs", () => {
    const help = slashHelpText({ webSearch: true, byok: true });
    expect(help).not.toContain("/digisearch —");
    expect(help).not.toContain("/digivault —");
    expect(help).not.toContain("/websearch —");
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

  it("normalises whitespace and case like the other code guards", () => {
    // isEffortCode / isViewCode / isSearchEngine / isThinkingCode all trim and
    // lowercase; a language code pasted from a settings export must not be the
    // one guard that says no.
    expect(isLangCode(" NL ")).toBe(true);
    expect(isLangCode("Nl")).toBe(true);
    expect(isLangCode(" DE ")).toBe(false);
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

describe("view-level wording", () => {
  it("gives every live level a wording and no retired level a label", () => {
    // The shared map is the one home of the wording (DIG-4665): the composer
    // menu's /view page and the palette's /view choice options both read it.
    // A level with no wording renders a blank description column; a retired
    // level with one keeps a dead id alive.
    expect(Object.keys(VIEW_LABELS).sort()).toEqual([...VIEW_CODES].sort());
    for (const code of VIEW_CODES) {
      expect(VIEW_LABELS[code].trim()).not.toBe("");
    }
    // `hidden` was retired in #6079, `compact` / `detailed` in #6034.
    for (const retired of ["hidden", "compact", "detailed"]) {
      expect(Object.keys(VIEW_LABELS)).not.toContain(retired);
    }
  });

  it("builds the /view choice options from the same map", () => {
    expect(VIEW_CHOICES).toEqual(
      VIEW_CODES.map((code) => ({ value: code, label: VIEW_LABELS[code] })),
    );
    // The palette's /view command must read that list, not a list of its own.
    // A hand-written list in the command def is a second copy of the wording
    // inside the package that owns the wording, and nothing else would see
    // it: the choice options are rendered by no surface today.
    expect(SLASH_COMMANDS.find((c) => c.id === "view")?.choiceOptions).toBe(VIEW_CHOICES);
    const density = SLASH_COMMANDS.find((c) => c.id === "density");
    expect(density).toMatchObject({
      id: "density",
      names: ["/density"],
      category: "setup",
    });
    expect(density?.choiceOptions?.map((choice) => choice.value)).toEqual([
      "compact",
      "default",
      "airy",
    ]);
  });

  it("prints the wording the product prints today", () => {
    // The golden words. The map is the one home of the wording, so the words
    // themselves are pinned here: a reworded level is a user-visible change
    // and must be a deliberate edit, not a side effect of a rename.
    expect(VIEW_LABELS).toEqual({
      quiet: "Quiet \u00b7 titles only",
      balanced: "Balanced \u00b7 open while it runs",
      verbose: "Verbose \u00b7 everything open",
    });
  });
});

describe("palette frame", () => {
  it("never opens a slash palette and a pane together", () => {
    for (const text of ["/", "/lang", "/language", "/language ", "/language English", "/language /", "/theme dark"]) {
      const surfaces = paletteSurfaces(text);
      expect(Number(surfaces.slash) + Number(surfaces.menu != null)).toBe(1);
    }
    expect(paletteSurfaces("hello")).toEqual({ slash: false, menu: null });
  });

  it("keeps a second slash inside the open pane", () => {
    expect(paletteSurfaces("/language ")).toEqual({ slash: false, menu: "language" });
    expect(paletteSurfaces("/language /")).toEqual({ slash: false, menu: "language" });
    expect(paletteFrame("/language /")).toMatchObject({ kind: "pane", filter: "/" });
  });

  it("syncs /language and /theme both ways", () => {
    expect(paneDraftForId("language")).toBe("/language ");
    expect(paneDraftForId("theme")).toBe("/theme ");
    expect(optionDraft("/language", "English")).toBe("/language English");
    expect(paletteFrame("/language")).toMatchObject({ kind: "commands", filter: "language" });
    expect(paletteFrame("/language English")).toMatchObject({
      kind: "pane",
      menu: "language",
      filter: "English",
    });
    expect(paletteFrame("/theme default dark")).toMatchObject({
      kind: "pane",
      menu: "theme",
      filter: "default dark",
    });
    const back = applyPaletteFrame("pane", paletteFrame("/language"));
    expect(back).toEqual({ kind: "commands", menu: "close", filter: "" });
    expect(applyPaletteFrame("closed", { kind: "closed" })).toEqual({
      kind: "closed",
      menu: "keep",
      filter: "",
    });
  });

  it("filters a pane without collapsing an exact option", () => {
    const rows = [
      { id: "en", token: "English", label: "en  English" },
      { id: "nl", token: "Dutch", label: "nl  Dutch" },
      { id: "sl", token: "Slovenian", label: "sl  Slovenian" },
    ];
    expect(submenuRows(rows, "eng").rows.map((row) => row.id)).toEqual(["en"]);
    expect(submenuRows(rows, "English")).toEqual({ rows, cursor: 0 });
    expect(submenuRows(rows, "en").rows.map((row) => row.id)).toEqual(["en"]);
  });
});

describe("/artifacts visibility", () => {
  it("lists /artifacts only when the surface is declared", () => {
    const withSurface = matchingSlashCommands("/", { artifacts: true }).map((c) => c.id);
    expect(withSurface).toContain("artifacts");
    // Without the flag the row is hidden, so a surface can never be implied.
    expect(matchingSlashCommands("/", {}).map((c) => c.id)).not.toContain("artifacts");
    expect(matchingSlashCommands("/", { artifacts: false }).map((c) => c.id)).not.toContain(
      "artifacts",
    );
  });
});
