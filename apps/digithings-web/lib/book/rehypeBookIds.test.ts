import { describe, expect, it } from "vitest";

import rehypeBookIds, { slugifyHeading } from "./rehypeBookIds.mjs";
import { extractHeadings, slugify } from "./headings.ts";

/**
 * The plugin duplicates the slug rules from `headings.ts` because
 * `next.config.mjs` cannot load a `.ts` file. This is the pin that stops the
 * copy drifting: if either side changes its alphabet, its dedupe suffix, or
 * its override handling, one of these cases fails.
 */

const heading = (level: number, children: string[]) => ({
  type: "element",
  tagName: `h${level}`,
  properties: {},
  children: children.map((value) => ({ type: "text", value })),
});

const run = (nodes: object[]) => {
  const tree = { type: "root", children: nodes };
  rehypeBookIds()(tree as never);
  return nodes as Array<{ properties: { id?: string } }>;
};

// ONE expected id per unique heading. The dedupe suffix is deliberately NOT in
// this table: `it.each` gives every row a fresh plugin, so a repeated heading
// asked to produce `-2` in isolation would fail for a reason that says nothing
// about the code. Dedupe is a whole-document property and is asserted as one,
// on the full corpus, below.
const CORPUS: Array<[number, string, string]> = [
  [2, "Why the book exists", "why-the-book-exists"],
  [2, "Che cos'è Paged.js?", "che-cos-e-paged-js"],
  [2, "Paged.js 0.4 — notes", "paged-js-0-4-notes"],
  [2, "***", "section"],
  [3, "A sub-section", "a-sub-section"],
  [4, "  Trimmed edges  ", "trimmed-edges"],
];

// The full document, where the same heading appears twice.
const DOCUMENT = [...CORPUS, [2, "Why the book exists", ""] as [number, string, string]];

describe("the plugin and the extractor agree", () => {
  it.each(CORPUS)("h%d %j", (level, text, expected) => {
    const node = run([heading(level, [text])])[0];
    expect(node.properties.id).toBe(expected);
  });

  it("derives the same ids as the extractor for a whole document, dedupe included", () => {
    const body = DOCUMENT.map(([level, text]) => `${"#".repeat(level)} ${text}`).join("\n\n");
    const fromExtractor = extractHeadings(body).map((h) => h.id);
    const fromPlugin = run(DOCUMENT.map(([level, text]) => heading(level, [text]))).map(
      (n) => n.properties.id,
    );
    expect(fromPlugin).toEqual(fromExtractor);
    // And the repeat really is in there, so the equality above is not two
    // empty lists: this is the assertion that would fail first.
    expect(fromPlugin.filter((id) => (id ?? "").startsWith("why-the-book-exists"))).toEqual([
      "why-the-book-exists",
      "why-the-book-exists-2",
    ]);
  });

  it("slugs identically", () => {
    for (const text of ["Why the book exists", "Che cos'è Paged.js?", "***", "Paged.js 0.4 — notes"]) {
      expect(slugifyHeading(text)).toBe(slugify(text));
    }
  });

  // Control: the corpus above would pass vacuously if the dedupe never ran, so
  // the repeated heading is the case that fails first when it breaks.
  it("CONTROL: the repeated heading is disambiguated in document order", () => {
    expect(run(DOCUMENT.map(([level, text]) => heading(level, [text]))).map((n) => n.properties.id)).toContain(
      "why-the-book-exists-2",
    );
  });

  it("leaves a non-heading element alone", () => {
    const p = { type: "element", tagName: "p", properties: {}, children: [{ type: "text", value: "x" }] };
    run([p]);
    expect((p as { properties: { id?: string } }).properties.id).toBeUndefined();
  });
});

