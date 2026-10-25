import { existsSync } from "node:fs";
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
  it("has a printed edition on disk", () => {
    expect(existsSync(join(process.cwd(), "public", "book", "the-digithings-book.pdf"))).toBe(true);
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
