import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { TRACE_LOCALES, createTraceT, resolveTraceLocale } from "./core";
import { workStatusText } from "../gallery-thread/work-status";
import { toolRowStatus } from "../trace-grouping/tool-row";
import { en } from "./locales/en";

describe("trace i18n tables", () => {
  it("every locale covers every key and its language's plural categories", () => {
    for (const [code, table] of Object.entries(TRACE_LOCALES)) {
      expect(Object.keys(table).sort(), code).toEqual(Object.keys(en).sort());
      const cats = new Intl.PluralRules(code).resolvedOptions().pluralCategories;
      for (const [key, value] of Object.entries(table)) {
        if (typeof value === "string") continue;
        for (const cat of cats) {
          if (cat === "other") continue;
          // `many` for FR is the 1e6 form; required so plural rules never fall back silently.
          expect(value[cat as Intl.LDMLPluralRule], `${code}.${key}.${cat}`).toBeTruthy();
        }
      }
    }
  });

  it("plural rules: EN and FR counts", () => {
    const tEn = createTraceT("en");
    const tFr = createTraceT("fr-FR");
    expect(tEn.plural("toolCalls", 1)).toBe("1 tool call");
    expect(tEn.plural("toolCalls", 2)).toBe("2 tool calls");
    expect(tFr.plural("toolCalls", 1)).toBe("1 appel d’outil");
    expect(tFr.plural("toolCalls", 2)).toBe("2 appels d’outils");
    expect(tFr.plural("usedTools", 0)).toBe("0 outil utilisé"); // FR: 0 is singular
    expect(tFr.plural("usedTools", 3)).toBe("3 outils utilisés");
  });

  it("unknown languages fall back to English", () => {
    expect(resolveTraceLocale("xx")).toBe("en");
    expect(createTraceT("de").t("thinking")).toBe("Thinking");
  });

  it("status lines switch with the locale", () => {
    const parts = [
      { type: "reasoning", status: { type: "complete" } },
      { type: "tool-call", toolName: "web_search", status: { type: "complete" } },
    ] as never;
    expect(workStatusText(parts, [0, 1], createTraceT("en")).label).toBe("Used 1 tool");
    expect(workStatusText(parts, [0, 1], createTraceT("fr")).label).toBe("1 outil utilisé");
    const running = { type: "running" } as never;
    expect(toolRowStatus(running, createTraceT("fr")).label).toBe("Outil en cours");
    expect(toolRowStatus({ type: "requires-action", reason: "tool-calls" }, createTraceT("en")).label).toBe(
      "Waiting on tool",
    );
  });
});

/** Files that render the chat trace. Their user-facing words must come from the tables. */
const TRACE_FILES = [
  "skins/base/elements/work-chain.tsx",
  "trace-grouping/tool-row.ts",
  "trace-grouping/use-work-chain.ts",
  "skins/base/aui-default/reasoning.tsx",
  "skins/base/aui-default/tool-fallback.aui.tsx",
  "skins/base/aui-default/tool-group.aui.tsx",
  "stock/reasoning.tsx",
  "stock/tool-fallback.aui.tsx",
  "stock/tool-group.aui.tsx",
  "gallery-thread/reasoning.tsx",
  "gallery-thread/work-chain.tsx",
  "gallery-thread/work-status.ts",
  "gallery-thread/private-work-step.tsx",
];

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
}

describe("no hardcoded trace strings", () => {
  const root = join(__dirname, "..");
  const phrases = new Set<string>();
  for (const value of Object.values(en)) {
    const texts = typeof value === "string" ? [value] : Object.values(value);
    for (const text of texts) {
      for (const piece of text!.split(/\{\w+\}/)) {
        const p = piece.trim();
        // Capitalised or multi-word phrases: user-facing copy, not identifiers.
        if (p.length >= 4 && (/[A-Z]/.test(p) || p.includes(" "))) phrases.add(p);
      }
    }
  }

  it("the trace file list is still current", () => {
    for (const f of TRACE_FILES) expect(() => readFileSync(join(root, f), "utf8")).not.toThrow();
    expect(readdirSync(join(__dirname, "locales"))).toContain("fr.ts");
  });

  it.each(TRACE_FILES)("%s uses the string table", (file) => {
    const src = stripComments(readFileSync(join(root, file), "utf8"));
    const hits: string[] = [];
    for (const phrase of phrases) {
      const esc = phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      // A quoted literal, a template literal, or JSX text containing the phrase.
      const re = new RegExp(`["'\`][^"'\`\\n]*\\b${esc}\\b[^"'\`\\n]*["'\`]|(?<![=-])>\\s*[^<{\\n]*\\b${esc}\\b`);
      const m = src.match(re);
      if (m && !/data-slot|className|aria-|slot=|\.displayName/.test(m[0])) hits.push(m[0]);
    }
    expect(hits).toEqual([]);
  });
});
