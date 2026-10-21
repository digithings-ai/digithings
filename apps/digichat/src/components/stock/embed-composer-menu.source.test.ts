import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "embed-composer-menu.tsx"), "utf8");

/** The one import the view wording may come from. */
const sharedImport =
  /import\s*\{[^}]*\bVIEW_LABELS\b[^}]*\}\s*from\s*"@digithings\/digichat-ui"/g;

/** The one import the house backend id may come from. */
const houseBackendImport =
  /import\s*\{[^}]*\bHOUSE_BACKEND_ID\b[^}]*\}\s*from\s*"@\/lib\/provider-label"/g;

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

/**
 * The house backend id has one home: `@/lib/provider-label`.
 *
 * The provider menu lists the house backend as one provider choice among the
 * own-key ones. It used to write the id inline, twice - as the row id and as
 * the row label - while the composer chip read it from the constant, so the
 * two named the same backend from two places of their own and could drift
 * apart (DIG-4887).
 *
 * The behaviour test cannot see a private copy come back: a copy that
 * carries today's id renders today's id, so the picker test cannot tell a
 * copy from the constant. So the source is pinned here instead, the way the
 * view wording is pinned above. The rule that the id is written in one
 * module only is held once, for the whole app, in
 * `src/lib/route-client-config.source.test.ts`.
 */
describe("EmbedComposerMenu house backend id", () => {
  it("reads the house backend id from the shared constant", () => {
    // The row id and the row label both come from the constant. A copy of
    // the id - written inline, declared or shadowed - would name the value
    // instead, and the app-wide rule would catch it.
    expect(source).toMatch(/id:\s*HOUSE_BACKEND_ID\b/);
    expect(source).toMatch(/label:\s*slashName\(HOUSE_BACKEND_ID\)/);
  });

  it("reads the house backend id from its one home", () => {
    // The constant is imported once, from the module that declares it.
    expect(source.match(houseBackendImport) ?? []).toHaveLength(1);
  });
});
