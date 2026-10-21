import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "embed-composer-menu.tsx"), "utf8");

/** The one import the view wording may come from. */
const sharedImport =
  /import\s*\{[^}]*\bVIEW_LABELS\b[^}]*\}\s*from\s*"@digithings\/digichat-ui"/g;

/**
 * The view-level wording has one home: `@digithings/digichat-ui`. A second,
 * private copy inside this component is exactly what let the #6034 rename
 * (compact/detailed -> quiet/verbose) leave the /view page without a
 * description (DIG-4665).
 *
 * The behaviour test cannot see a private copy come back: a private copy
 * that carries the right words renders the right words. So the source is
 * pinned here instead.
 *
 * The rule itself - no private copy, no blank-line fallback - is held once,
 * for the whole app, in `src/lib/view-labels.one-home.test.ts`. What is
 * left here is what is true of this file alone: it reads the wording from
 * the shared package, and it reads the shared map.
 */
describe("EmbedComposerMenu view labels", () => {
  it("reads the wording from the shared package", () => {
    expect(source.match(sharedImport)).toHaveLength(1);
  });

  it("looks the wording up in the shared map", () => {
    const lookupLines = source
      .split("\n")
      .filter((line) => /\bVIEW_LABELS\b/.test(line) && !/^\s*import\b/.test(line));
    expect(lookupLines.length).toBeGreaterThan(0);
  });
});
