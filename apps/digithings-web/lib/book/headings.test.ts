import { describe, expect, it } from "vitest";

import { extractHeadings, headingText, slugify } from "./headings";

describe("slugify", () => {
  it("lowercases, joins words with single hyphens and trims the edges", () => {
    expect(slugify("  Running headers and page numbers  ")).toBe("running-headers-and-page-numbers");
  });

  it("folds accents so a heading in a European language still anchors", () => {
    expect(slugify("Che cos'è Paged.js?")).toBe("che-cos-e-paged-js");
  });

  // A heading of only punctuation produced "" before, which is not a valid
  // anchor and produced a ToC link to the top of the page.
  it("never returns an empty slug", () => {
    expect(slugify("***")).toBe("section");
    expect(slugify("—")).toBe("section");
  });

  it("keeps digits and collapses runs of separators", () => {
    expect(slugify("Paged.js 0.4 — notes")).toBe("paged-js-0-4-notes");
  });
});

describe("headingText", () => {
  it("drops inline markdown but keeps the words", () => {
    expect(headingText("The **`svg` pan** and zoom")).toBe("The svg pan and zoom");
  });

  it("unwraps a link to its label", () => {
    expect(headingText("See [the ToC](/book/) rules")).toBe("See the ToC rules");
  });
});

describe("extractHeadings", () => {
  const body = [
    "# Chapter title",
    "",
    "## Why the book exists",
    "",
    "text",
    "",
    "### A sub-section",
    "",
    "## Why the book exists",
    "",
    "## What each part buys you",
  ].join("\n");

  it("returns headings in document order with their levels", () => {
    const h = extractHeadings(body);
    expect(h.map((x) => [x.level, x.text])).toEqual([
      [1, "Chapter title"],
      [2, "Why the book exists"],
      [3, "A sub-section"],
      [2, "Why the book exists"],
      [2, "What each part buys you"],
    ]);
  });

  it("derives every id from the heading's own words", () => {
    expect(extractHeadings(body).map((h) => h.id)).toEqual([
      "chapter-title",
      "why-the-book-exists",
      "a-sub-section",
      "why-the-book-exists-2",
      "what-each-part-buys-you",
    ]);
  });

  // Two entries with the same id would make the second ToC link jump to the
  // first, which is a dead link that renders as working.
  it("disambiguates a repeated heading with a -2 suffix", () => {
    const ids = extractHeadings("## Notes\n\n## Notes\n\n## Notes\n").map((h) => h.id);
    expect(ids).toEqual(["notes", "notes-2", "notes-3"]);
    expect(new Set(ids).size).toBe(3);
  });

  it("does not treat a comment line inside a fenced block as a heading", () => {
    const withCode = ["## Real", "", "```sh", "# not a heading", "```", "", "## Also real"].join("\n");
    expect(extractHeadings(withCode).map((h) => h.text)).toEqual(["Real", "Also real"]);
  });

  it("ignores a closing fence that a longer opening fence would not close", () => {
    // ```` opens a 4-backtick fence; the ``` inside it is code.
    const body2 = ["````md", "```", "## Still code", "```", "````", "", "## Heading"].join("\n");
    expect(extractHeadings(body2).map((h) => h.text)).toEqual(["Heading"]);
  });

  it("strips the closing hash run of a setext-looking ATX heading", () => {
    expect(extractHeadings("## Closed ###\n").map((h) => h.text)).toEqual(["Closed"]);
  });
});