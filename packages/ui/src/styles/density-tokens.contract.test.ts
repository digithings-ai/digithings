import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  DENSITY_TOKENS,
  TRACE_DENSITIES,
  TRACE_SPACING,
  TRACE_SPACE_SCALE,
} from "../components/chat/trace-spacing";

/**
 * One density set, two files. `chat-aui.css` declares the `--density-*` custom
 * properties on `.digichat-thread`; `trace-spacing.ts` mirrors them for the
 * palette, the mobile default and anything that cannot read CSS. This pins the
 * two together per mode — a mode that edits one without the other fails here.
 */

const here = dirname(fileURLToPath(import.meta.url));
const aui = readFileSync(join(here, "chat-aui.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const skin = readFileSync(join(here, "chat-digichat.css"), "utf8").replace(
  /\/\*[\s\S]*?\*\//g,
  "",
);

/** The base block is the second `.digichat-thread, .digichat-launcher` rule. */
function baseBlock(): string {
  const blocks = [...aui.matchAll(/\.digichat-thread,\s*\n\.digichat-launcher\s*\{([\s\S]*?)\n\}/g)];
  const density = blocks.map((m) => m[1]).filter((body) => body.includes("--density-gap-1:"));
  if (density.length !== 1) throw new Error(`expected one density base block, got ${density.length}`);
  return density[0];
}

function declarations(body: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const m of body.matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)) map.set(m[1], m[2].trim());
  return map;
}

const base = declarations(baseBlock());

function modeBlock(density: string): Map<string, string> {
  const match = aui.match(new RegExp(`([^{}]*data-density="${density}"[^{}]*)\\{([^{}]*)\\}`));
  if (!match?.[1]?.includes(".digichat-thread")) {
    throw new Error(`no .digichat-thread rule for data-density="${density}"`);
  }
  return declarations(match[2]);
}

/** Resolve `var(--x)` chains until a literal is reached. */
function resolve(raw: string, table: Map<string, string>, depth = 0): string {
  const value = raw.trim();
  const reference = value.match(/^var\(--([a-z0-9-]+)\)$/);
  if (!reference) return value;
  if (depth > 8) throw new Error(`var chain too deep at ${value}`);
  const next = table.get(reference[1]);
  if (next === undefined) throw new Error(`undeclared ${value}`);
  return resolve(next, table, depth + 1);
}

/** Base tokens overridden by the mode's own reassignment, as resolved literals. */
function effective(density: string): Map<string, string> {
  const table = new Map(base);
  for (const [name, value] of modeBlock(density)) table.set(name, value);
  const resolved = new Map<string, string>();
  for (const name of table.keys()) resolved.set(name, resolve(`var(--${name})`, table));
  return resolved;
}

const CSS_TO_FIELD = {
  "density-gap-1": "gap1",
  "density-gap-2": "gap2",
  "density-gap-3": "gap3",
  "density-gap-4": "gap4",
  "density-pad": "pad",
  "density-leading": "leading",
  "density-leading-tight": "leadingTight",
  "density-tracking": "tracking",
  "density-tracking-mono": "trackingMono",
} as const;

describe("density tokens", () => {
  it("declares the scale once, with the same values as TRACE_SPACE_SCALE", () => {
    for (const [step, value] of Object.entries(TRACE_SPACE_SCALE)) {
      expect(base.get(`trace-space-${step}`), `--trace-space-${step}`).toBe(value);
    }
    // The scale has no gaps and no extras.
    const declared = [...base.keys()].filter((name) => /^trace-space-\d+$/.test(name));
    expect(declared.sort()).toEqual(
      Object.keys(TRACE_SPACE_SCALE)
        .map((step) => `trace-space-${step}`)
        .sort(),
    );
  });

  it("mirrors DENSITY_TOKENS for every mode", () => {
    for (const density of TRACE_DENSITIES) {
      const values = effective(density);
      const tokens = DENSITY_TOKENS[density];
      for (const [cssName, field] of Object.entries(CSS_TO_FIELD)) {
        expect(values.get(cssName), `${density} --${cssName}`).toBe(
          tokens[field as keyof typeof tokens],
        );
      }
    }
  });

  it("keeps every --trace-* name working as an alias of the density set", () => {
    const fields: Array<[keyof typeof TRACE_SPACING[typeof TRACE_DENSITIES[number]], string]> = [
      ["titleGap", "density-gap-3"],
      ["groupGap", "density-gap-2"],
      ["withinGap", "density-gap-1"],
      ["bodyPad", "density-pad"],
      ["chainGap", "density-gap-4"],
    ];
    for (const density of TRACE_DENSITIES) {
      const values = effective(density);
      for (const [token, cssName] of fields) {
        expect(values.get(cssName), `${density} ${cssName}`).toBe(TRACE_SPACING[density][token]);
      }
      // headerGap and bodyIndent are the two that step independently.
      expect(values.get("trace-header-gap"), `${density} header gap`).toBe(
        TRACE_SPACING[density].headerGap,
      );
      expect(values.get("trace-body-indent"), `${density} body indent`).toBe(
        TRACE_SPACING[density].bodyIndent,
      );
    }
  });

  it("is declared only in chat-aui.css, scoped to the thread root", () => {
    for (const density of TRACE_DENSITIES) {
      expect(aui).toContain(`.digichat-thread[data-density="${density}"]`);
    }
    // The skin consumes the tokens; it never redeclares the set.
    expect(skin).not.toMatch(/--density-(gap|pad|leading|tracking)[a-z0-9-]*\s*:/);
    expect(skin).not.toContain("[data-density");
  });

  it("scales the composer padding from the same set", () => {
    expect(base.get("composer-padding")).toBe("calc(var(--density-pad) + 0.5rem)");
    // The only px composer padding left is the folded compact layout's override.
    expect(aui).not.toMatch(/--composer-padding:\s*8px/);
  });
});

describe("composer padding token", () => {
  it("is loaded by every shell that mounts the gallery Thread", () => {
    // apps/reference/(chatbot) mounts the Thread and imports chat-digichat.css,
    // but never app/globals.css — so its shell must load chat-aui.css itself or
    // var(--composer-padding) is undefined and the composer padding resolves to 0.
    const shell = readFileSync(
      join(here, "../../../../apps/reference/app/(chatbot)/chatbot-shell.css"),
      "utf8",
    );
    expect(shell).toContain('@import "@digithings/ui/styles/chat-aui.css";');
  });
});
