import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { VIEW_LABELS } from "@digithings/digichat-ui";

const here = dirname(fileURLToPath(import.meta.url));
const appSrc = join(here, "..");

/** Every app source file, tests excluded. */
function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    if (!/\.tsx?$/.test(entry.name)) return [];
    if (/\.test\.tsx?$/.test(entry.name)) return [];
    return [full];
  });
}

function read(file: string): string {
  return readFileSync(file, "utf8");
}

/**
 * The view-level wording has one home: `@digithings/digichat-ui`. A private
 * copy of it inside the app is exactly what let the #6034 rename
 * (compact/detailed -> quiet/verbose) leave the composer menu's `/view` page
 * without a description (DIG-4665).
 *
 * The rule is held here, once, for the whole app: no app module holds the
 * wording, no app module declares a view label map of its own, and no app
 * module falls back on the shared map. The component's own file cannot see a
 * copy that lives somewhere else, so the rule is not checked there too. A
 * module that needs the wording imports the shared map.
 *
 * The scan covers the app sources under `apps/digichat/src`, test files
 * excluded: the rule is about app modules, and the test files are where the
 * wording is quoted on purpose.
 */
describe("the view-level wording has one home", () => {
  const files = sourceFiles(appSrc);

  it("finds the app sources to scan", () => {
    expect(files.length).toBeGreaterThan(50);
  });

  it("keeps the wording out of the app", () => {
    const copies = files.filter((file) =>
      Object.values(VIEW_LABELS).some((wording) => read(file).includes(wording)),
    );
    expect(copies.map((file) => relative(appSrc, file))).toEqual([]);
  });

  it("keeps a private view label map out of the app", () => {
    // A map of the view wording, whatever it is called: `VIEW_LABELS`,
    // `LEVEL_LABELS`, `MY_VIEW_LABELS`, `VIEW_LABEL_TEXT`, `viewLabels`.
    // The keyword must be a word of its own, so `OVERVIEW_LABELS` is not a
    // view map.
    const copies = files.filter((file) =>
      /(?:const|let|var|function)\s+\w*(?<![A-Za-z])(?:VIEW|LEVEL)\w*(?:LABELS?|DESCRIPTIONS?)\w*/i.test(
        read(file),
      ),
    );
    expect(copies.map((file) => relative(appSrc, file))).toEqual([]);
  });

  it("keeps a blank-line fallback on the shared map out of the app", () => {
    // `VIEW_LABELS[id] ?? ""` (or `|| ""`) turns a missing wording into an
    // empty description column instead of a compile error. The fallback sat
    // on the line that reads the map, so the line is what is checked, and it
    // is checked in every app module. The rule keys on the shared map by
    // name, so a module that imports it under another name is a rule this
    // check does not see.
    const copies = files.filter((file) =>
      read(file)
        .split("\n")
        .some(
          (line) =>
            /\bVIEW_LABELS\b/.test(line) &&
            !/^\s*import\b/.test(line) &&
            /\?\?|\|\|/.test(line),
        ),
    );
    expect(copies.map((file) => relative(appSrc, file))).toEqual([]);
  });
});
