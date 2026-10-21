import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "embed-composer-menu.tsx"), "utf8");

/** The file without its import statements: the imports are checked apart. */
const body = source.replace(/import\s+[^;]*?;/g, "");

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
 * pinned here instead. The checks are deliberately about the shape of the
 * file, not about one line of it, so a rename of a variable or a helper
 * around the lookup does not fail the build.
 */
describe("EmbedComposerMenu view labels", () => {
  it("reads the wording from the shared package", () => {
    expect(source.match(sharedImport)).toHaveLength(1);
  });

  it("keeps no private copy of the view label map", () => {
    // A local map, whatever it is called: `VIEW_LABELS`, `LEVEL_LABELS`, ...
    expect(body).not.toMatch(/(?:const|let|var|function)\s+\w*VIEW\w*LABELS?\b/);
    expect(body).not.toMatch(/\bVIEW_LABELS\s*:/);
  });

  it("has no blank-line fallback on the label lookup", () => {
    // `?? ""` turns a missing wording into an empty description column
    // instead of a compile error. The fallback sat on the lookup line
    // (`value: VIEW_LABELS[id] ?? ""`), so the line is what is checked.
    const lookupLines = source
      .split("\n")
      .filter((line) => /\bVIEW_LABELS\b/.test(line) && !/^\s*import\b/.test(line));
    expect(lookupLines.length).toBeGreaterThan(0);
    for (const line of lookupLines) {
      expect(line).not.toMatch(/\?\?/);
    }
  });
});
