import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// Single `__dirname` usage: the tsconfig carries no node types, so this file
// reports TS2304 for it (pre-existing, like its node: imports — see
// contrast.contract.test.ts).
const here = __dirname;
const repoRoot = path.resolve(here, "../../../..");
const at = (rel: string) => readFileSync(path.join(repoRoot, rel), "utf8");

const tokens = at("packages/design/tokens.css");
const digichatTheme = at("packages/ui/src/styles/digichat-app-theme.css");

/**
 * One font config per surface (DIG-2375). `config` is the single file allowed
 * to call `next/font` for that surface: swap the face by editing the loader it
 * names, and nothing else in the repo changes.
 */
const SURFACES = [
  { surface: "dashboard", config: "apps/dashboard/app/fonts.ts" },
  { surface: "digiquant.io", config: "apps/digiquant-web/app/fonts.ts" },
  { surface: "digiquant app", config: "apps/digiquant-app/app/fonts.ts" },
  { surface: "digithings.ai", config: "apps/digithings-web/app/fonts.ts" },
  { surface: "DigiChat", config: "apps/digichat/src/app/fonts.ts" },
] as const;

/** Type-specimen galleries and demos show font alternatives on purpose. */
const OUT_OF_SCOPE = [
  "apps/reference/",
  "apps/digichat/reference/",
  "packages/design/demos/",
  "packages/design/references/",
];

function filesUnder(root: string): string[] {
  const abs = path.join(repoRoot, root);
  if (!existsSync(abs)) return [];
  const out: string[] = [];
  for (const entry of readdirSync(abs, { withFileTypes: true })) {
    const rel = `${root}/${entry.name}`;
    if (entry.isDirectory()) out.push(...filesUnder(rel));
    else out.push(rel);
  }
  return out;
}

/** Every source file the font decision can reach, minus the galleries. */
const IN_SCOPE = [...filesUnder("apps"), ...filesUnder("packages")]
  .filter((file) => /\.(ts|tsx|css|html|md|svg)$/.test(file))
  .filter((file) => !OUT_OF_SCOPE.some((dir) => file.startsWith(dir)));

/** Slice the first `:root[data-theme] { … }` block (top-level braces only). */
function themedRoot(): string {
  const start = tokens.indexOf(":root[data-theme]");
  expect(start, "tokens.css has a bare :root[data-theme] block").toBeGreaterThan(-1);
  let depth = 0;
  let i = tokens.indexOf("{", start);
  for (; i < tokens.length; i++) {
    if (tokens[i] === "{") depth++;
    else if (tokens[i] === "}") {
      depth--;
      if (depth === 0) break;
    }
  }
  return tokens.slice(start, i + 1);
}

/**
 * Geist Mono ships no U+25B8 / U+25BE (nav-tree triangles) and no U+2318
 * (command key). A bare `var(--font-mono-face)` as a whole font-family would
 * drop every glyph Geist lacks onto the browser default, so every stack keeps a
 * real system fallback chain behind the face.
 */
const FALLBACK_CHAIN = ["ui-monospace", "SF Mono", "Menlo", "DejaVu Sans Mono", "Segoe UI Symbol"];

describe("font tokens contract", () => {
  it("gives every surface one config file that loads Geist Mono as the mono face", () => {
    for (const { surface, config } of SURFACES) {
      expect(existsSync(path.join(repoRoot, config)), `${surface} has ${config}`).toBe(true);
      const source = at(config);
      expect(source, `${config} calls next/font`).toMatch(/from ["']next\/font/);
      expect(source, `${config} loads Geist Mono`).toMatch(/Geist_Mono\(\{/);
      expect(source, `${config} sets the generic mono face var`).toMatch(
        /Geist_Mono\(\{[^}]*variable:\s*["']--font-mono-face["']/,
      );
      expect(source, `${config} exports fontVariables`).toMatch(/export const fontVariables/);
    }
  });

  it("keeps next/font out of every file but the surface configs", () => {
    const allowed = new Set<string>(SURFACES.map((s) => s.config));
    const callers = IN_SCOPE.filter((file) => /from ["']next\/font/.test(at(file)));
    expect(callers.filter((file) => !allowed.has(file))).toEqual([]);
  });

  it("retires the JetBrains and IBM Plex Mono variables everywhere", () => {
    const retired =
      /jetbrains|plex\s?mono|IBM_Plex_Mono|--font-jbmono|--font-ibm-plex-mono|--font-jetbrains-mono/i;
    expect(IN_SCOPE.filter((file) => retired.test(at(file)))).toEqual([]);
  });

  it("builds the mono stack once in tokens.css, behind a face var", () => {
    expect(tokens).toMatch(
      /--font-stack-mono:\s*var\(--font-mono-face,\s*"Geist Mono"\)\s*,\s*ui-monospace/,
    );
    expect(tokens).toMatch(/--font-family-mono:\s*var\(--font-stack-mono\)/);
    expect(themedRoot()).toMatch(/--font-mono:\s*var\(--font-stack-mono\)/);
    expect(themedRoot()).toMatch(/--font-display:\s*var\(--font-stack-display\)/);
  });

  it("keeps the glyph fallback chain on every mono stack", () => {
    for (const chain of FALLBACK_CHAIN) {
      expect(tokens, `tokens.css mono stack falls back to ${chain}`).toContain(chain);
      expect(digichatTheme, `digichat mono stack falls back to ${chain}`).toContain(chain);
    }
    // A stack may never be the bare face var: that loses every glyph the face lacks.
    for (const source of [tokens, digichatTheme]) {
      expect(source).not.toMatch(/:\s*var\(--font-(?:sans|mono|display)-face\)\s*;/);
    }
  });

  it("aliases --font-geist-mono to the mono face so the chat skin keeps working", () => {
    expect(digichatTheme).toMatch(/--font-geist-mono:\s*var\(--font-mono-face\)/);
  });
});