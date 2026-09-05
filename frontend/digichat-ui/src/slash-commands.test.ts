import { describe, expect, it } from "vitest";
import {
  formatCliSettingLine,
  isLangCode,
  LANG_LABELS,
  matchingSlashCommands,
  nextPaletteIndex,
  parseSlashInput,
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
      command: { id: "vault", forceTool: "digivault_search_notes" },
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

  it("aliases /digisearch and /digivault onto the public commands", () => {
    expect(parseSlashInput("/digisearch jwt")).toMatchObject({
      kind: "command",
      command: { id: "search", forceTool: "digisearch" },
      arg: "jwt",
    });
    expect(parseSlashInput("/digivault original notes")).toMatchObject({
      kind: "command",
      command: { id: "vault", forceTool: "digivault_search_notes" },
      arg: "original notes",
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
  });

  it("flags unknown commands", () => {
    expect(parseSlashInput("/web")).toEqual({ kind: "unknown", name: "/web" });
  });
});

describe("matchingSlashCommands", () => {
  it("lists public copy for a bare slash including Vault / Web search / BYOK / Settings", () => {
    const matches = matchingSlashCommands("/", { webSearch: true, byok: true });
    const hints = matches.map((c) => c.hint);
    expect(hints).toContain("Search the knowledge base");
    expect(hints).toContain("Vault");
    expect(hints).toContain("Web search");
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
  });
});

describe("slashHelpText", () => {
  it("uses public Vault copy, not Docs or raw tool ids", () => {
    const help = slashHelpText({ webSearch: true, byok: true });
    expect(help).toContain("/search — Search the knowledge base");
    expect(help).toContain("/vault — Vault");
    expect(help).toContain("/websearch — Web search");
    expect(help).toContain("/byok — BYOK");
    expect(help).toContain("/settings — Settings");
    expect(help).not.toContain("digisearch");
    expect(help).not.toContain("digivault_get_note");
    expect(help).not.toContain("/docs —");
  });
});

describe("isLangCode", () => {
  it("accepts the curated list only", () => {
    expect(isLangCode("de")).toBe(true);
    expect(isLangCode("klingon")).toBe(false);
  });
});

describe("LANG_LABELS", () => {
  it("names every curated code in English", () => {
    expect(LANG_LABELS.de).toBe("German");
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
