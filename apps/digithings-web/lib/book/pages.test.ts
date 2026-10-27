import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import pages from "./generated/pages.json";

/**
 * `/book` scrolls the paginated document and labels it from the map the print
 * pass writes. The page numbers and the paper come from the same pass, so this
 * pins the map to a map that could have come from a book: chapters only on
 * pages that exist, and a printed edition on disk.
 */
describe("the paginated book", () => {
  /**
   * The printed file is a snapshot: editing a chapter does not reprint it. This
   * pins the snapshot to the text, so a content change that forgets to reprint
   * fails here instead of shipping a book whose PDF disagrees with the page.
   */
  it("was printed from the text it is committed beside", () => {
    const root = join(process.cwd(), "content", "book");
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true }).sort((a, b) =>
        a.name.localeCompare(b.name),
      )) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (entry.name.endsWith(".mdx")) files.push(full);
      }
    };
    walk(root);
    const hash = createHash("sha256");
    for (const file of files) {
      hash.update(file.slice(root.length));
      hash.update(readFileSync(file));
    }
    const expected = (pages as { contentHash?: string }).contentHash;
    expect(expected, "pages.json carries no contentHash").toBeTruthy();
    expect(hash.digest("hex").slice(0, 16)).toBe(expected);
  });

  it("has every printed edition on disk", () => {
    const editions = (pages as { editions?: { file: string }[] }).editions ?? [];
    expect(editions.length).toBeGreaterThan(0);
    for (const edition of editions) {
      expect(existsSync(join(process.cwd(), "public", "book", edition.file)), edition.file).toBe(
        true,
      );
    }
  });

  it("puts every chapter on a page that exists", () => {
    const slugs = Object.keys(pages.map);
    expect(slugs.length).toBeGreaterThan(0);
    for (const slug of slugs) {
      const page = pages.map[slug as keyof typeof pages.map];
      expect(page, slug).toBeGreaterThan(1);
      expect(page, slug).toBeLessThanOrEqual(pages.pages);
    }
  });
});
