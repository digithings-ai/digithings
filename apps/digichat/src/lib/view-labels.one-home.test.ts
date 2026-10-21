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
 * The guard on the component's own file cannot see a copy that lives
 * somewhere else, so the rule is checked across the app: no app module holds
 * the wording, and no app module declares a view label map of its own. A
 * module that needs the wording imports the shared map.
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
    const copies = files.filter((file) =>
      /(?:const|let|var|function)\s+\w*VIEW\w*LABELS?\b/.test(read(file)),
    );
    expect(copies.map((file) => relative(appSrc, file))).toEqual([]);
  });
});
