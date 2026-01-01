import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * Unbounded motion must honour `prefers-reduced-motion: reduce`.
 *
 * An `animation: … infinite` is the one kind of motion a visitor cannot wait
 * out — it runs for as long as the page is open. `reduce` is the signal that
 * says "do not do that", so every infinite animation the kit ships has to be
 * switched off under it. The dot in the tearsheet's live badge was the one that
 * was not: `finance-tearsheet.css` had a reduce block, but it only covered
 * `.ts-tab-pane`, so a pulsing indicator carried on pulsing (found on the
 * digithings.ai landing page, where the badge marks the synthetic digiquant
 * series). A reduce block existing is not the invariant — the *selector* being
 * covered is, which is what this asserts.
 *
 * Guards are collected across the whole kit rather than per file, because every
 * sheet here is imported into the same document: a rule in one sheet and its
 * guard in another still work at runtime.
 */

const here = dirname(fileURLToPath(import.meta.url));

/** `packages/design/site/site.css` — the shared site sheet the apps import. */
const SITE_SHEET = join(here, "..", "..", "..", "design", "site", "site.css");

/** Comments stripped, so a selector named in prose cannot satisfy an assertion. */
function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** Index of the `}` matching the `{` at `open`. */
function matchingBrace(css: string, open: number): number {
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}") {
      depth--;
      if (depth === 0) return i;
    }
  }
  throw new Error("unbalanced braces in stylesheet");
}

/** The bodies of every `@media (prefers-reduced-motion: reduce)` block. */
function reduceBlocks(css: string): string[] {
  const bodies: string[] = [];
  const re = /@media[^{]*prefers-reduced-motion:\s*reduce/g;
  for (let m = re.exec(css); m; m = re.exec(css)) {
    const open = css.indexOf("{", m.index);
    bodies.push(css.slice(open + 1, matchingBrace(css, open)));
  }
  return bodies;
}

/** Selectors that a reduce block switches off with `animation: none`. */
function guardedSelectors(css: string): Set<string> {
  const guarded = new Set<string>();
  for (const body of reduceBlocks(css)) {
    for (const rule of body.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
      if (/animation:\s*none/.test(rule[2])) {
        for (const selector of rule[1].split(",")) guarded.add(selector.trim());
      }
    }
  }
  return guarded;
}

/** Every rule whose body declares an animation that runs forever. */
function infiniteRules(css: string): { selector: string; declaration: string }[] {
  const found: { selector: string; declaration: string }[] = [];
  for (const rule of css.matchAll(/([^{}@]+)\{([^{}]*)\}/g)) {
    const declaration = /animation:[^;]*infinite/.exec(rule[2]);
    if (declaration) found.push({ selector: rule[1].trim(), declaration: declaration[0] });
  }
  return found;
}

function sheets(): { name: string; css: string }[] {
  const kit = readdirSync(here)
    .filter((file) => file.endsWith(".css"))
    .map((file) => ({
      name: `packages/ui/src/styles/${file}`,
      css: readFileSync(join(here, file), "utf8"),
    }));
  return [...kit, { name: "packages/design/site/site.css", css: readFileSync(SITE_SHEET, "utf8") }];
}

describe("kit motion honours prefers-reduced-motion", () => {
  const all = sheets();
  const guarded = new Set<string>();
  for (const sheet of all) {
    for (const selector of guardedSelectors(stripComments(sheet.css))) guarded.add(selector);
  }

  it("ships at least one infinite animation to guard (the scan is not vacuous)", () => {
    const total = all.reduce((n, sheet) => n + infiniteRules(stripComments(sheet.css)).length, 0);
    expect(total).toBeGreaterThan(0);
  });

  it.each(all.map((sheet) => [sheet.name, sheet] as const))(
    "disables every infinite animation in %s under reduce",
    (name, sheet) => {
      for (const rule of infiniteRules(stripComments(sheet.css))) {
        for (const selector of rule.selector.split(",")) {
          const s = selector.trim();
          expect(
            guarded.has(s),
            `${name}: \`${s}\` runs \`${rule.declaration}\` forever with no \`animation: none\` under prefers-reduced-motion: reduce`,
          ).toBe(true);
        }
      }
    },
  );
});
