import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const source = readFileSync(path.join(__dirname, "PagedBoot.tsx"), "utf8");

describe("PagedBoot", () => {
  it("hides the source document once pagination owns the output", () => {
    // Paged.js leaves the source beside the page boxes; in print that becomes
    // extra blank pages before the book. The hide and its cleanup must both
    // exist, or a client-side return to the route leaves a blank book.
    expect(source).toContain("content.hidden = true");
    expect(source).toContain("content.hidden = false");
  });

  it("waits for the reference pass before publishing completion", () => {
    expect(source.indexOf("fillTocPageRefs()")).toBeLessThan(
      source.indexOf("content.dataset.bookPaginated"),
    );
  });
});
