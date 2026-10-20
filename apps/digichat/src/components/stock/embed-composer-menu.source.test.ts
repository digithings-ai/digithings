import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "embed-composer-menu.tsx"), "utf8");

/**
 * The view-level wording has one home: `@digithings/digichat-ui`. A second,
 * private copy inside this component is exactly what let the #6034 rename
 * (compact/detailed -> quiet/verbose) leave the /view page without a
 * description (DIG-4665). The behaviour test cannot see a private copy come
 * back, so the source itself is pinned here.
 */
describe("EmbedComposerMenu view labels", () => {
  it("reads the wording from the shared package", () => {
    expect(source).toMatch(
      /import \{[^}]*VIEW_LABELS[^}]*\} from "@digithings\/digichat-ui"/,
    );
    expect(source).toMatch(/value: VIEW_LABELS\[id\]/);
  });

  it("keeps no private copy of the label map", () => {
    expect(source).not.toMatch(/const VIEW_LABELS/);
    expect(source).not.toMatch(/VIEW_LABELS\s*:/);
  });

  it("has no blank-line fallback on the label lookup", () => {
    // `?? ""` turns a missing wording into an empty description column
    // instead of a compile error.
    expect(source).not.toMatch(/VIEW_LABELS\[[^\]]+\]\s*\?\?/);
  });

  it("does not teach the retired level ids", () => {
    // The retired ids are `hidden` (retired in #6079), `compact` and
    // `detailed` (renamed in #6034). A quoted one here would be a level the
    // menu still offers after the product renamed it away.
    expect(source).not.toMatch(/["'`](compact|detailed|hidden)["'`]/);
  });
});
