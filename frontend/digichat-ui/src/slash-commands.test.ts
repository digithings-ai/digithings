import { describe, expect, it } from "vitest";
import {
  isLangCode,
  LANG_LABELS,
  matchingSlashCommands,
  parseSlashInput,
  slashHelpText,
} from "./slash-commands";

describe("parseSlashInput", () => {
  it("treats ordinary text as none", () => {
    expect(parseSlashInput("how does auth work")).toEqual({ kind: "none" });
  });

  it("waits on empty /search and /docs instead of sending", () => {
    const search = parseSlashInput("/search");
    expect(search).toMatchObject({ kind: "incomplete", prefix: "/search " });
    const docs = parseSlashInput("/docs   ");
    expect(docs).toMatchObject({ kind: "incomplete", prefix: "/docs " });
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
      command: { id: "docs", forceTool: "digivault_search_notes" },
      arg: "original notes",
    });
  });

  it("parses client-only /help /new /lang", () => {
    expect(parseSlashInput("/help")).toMatchObject({ kind: "command", command: { id: "help" } });
    expect(parseSlashInput("/new")).toMatchObject({ kind: "command", command: { id: "new" } });
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
  it("lists public copy for a bare slash", () => {
    const hints = matchingSlashCommands("/").map((c) => c.hint);
    expect(hints).toContain("Search the knowledge base");
    expect(hints).toContain("Find original documents");
  });

  it("narrows as the user types a prefix", () => {
    expect(matchingSlashCommands("/se").map((c) => c.id)).toEqual(["search"]);
    expect(matchingSlashCommands("/search foo")).toEqual([]);
  });
});

describe("slashHelpText", () => {
  it("uses public copy, not raw tool ids", () => {
    const help = slashHelpText();
    expect(help).toContain("/search — Search the knowledge base");
    expect(help).toContain("/docs — Find original documents");
    expect(help).not.toContain("digisearch");
    expect(help).not.toContain("digivault_get_note");
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
