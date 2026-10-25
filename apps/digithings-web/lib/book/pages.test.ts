import { existsSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import pages from "./generated/pages.json";

/**
 * `/book` shows the PDF's pages and labels them with the map the PDF build
 * writes. Those two facts come from different steps — `book:pdf` writes the
 * map, `book:pages` rasterises the files — so this pins them together: a page
 * in the map with no image is a blank sheet on the site, and an image with no
 * page in the map is a sheet nobody can link to.
 *
 * The book is printed twice, once per theme, and the reader swaps the image
 * source rather than colouring one edition with a filter. A theme whose images
 * are missing is a reader whose pages do not change with the site.
 */
describe("the paginated book", () => {
  const root = join(process.cwd(), "public", "book", "pages");
  const editions = { light: root, dark: join(root, "dark") } as const;

  for (const [theme, dir] of Object.entries(editions)) {
    it(`has as many ${theme} page images as the map says`, () => {
      const images = Array.from({ length: pages.pages }, (_, index) =>
        join(dir, `${String(index + 1).padStart(2, "0")}.webp`),
      );
      expect(pages.pages).toBeGreaterThan(0);
      expect(images.filter((file) => existsSync(file))).toHaveLength(pages.pages);
      expect(existsSync(join(dir, `${String(pages.pages + 1).padStart(2, "0")}.webp`))).toBe(false);
    });
  }

  it("has both printed editions on disk", () => {
    expect(existsSync(join(process.cwd(), "public", "book", "the-digithings-book.pdf"))).toBe(true);
    expect(
      existsSync(join(process.cwd(), "public", "book", "the-digithings-book-dark.pdf")),
    ).toBe(true);
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
