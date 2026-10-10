import { describe, expect, it } from "vitest";

import { extractHeadings } from "./headings";
import { chapterHref, chapterNeighbours, nestToc, orderChapters, readingOrder, sectionNeighbours, tocEntries } from "./toc";

const REF = (slug: string, order: number, title = slug) => ({
  slug,
  title,
  summary: "",
  order,
  href: chapterHref(slug),
  headingCount: 3,
});

describe("tocEntries", () => {
  it("keeps levels 2 to 4 and drops the chapter title", () => {
    const h = extractHeadings(["# Chapter", "## Two", "### Three", "#### Four", "##### Five"].join("\n"));
    expect(tocEntries(h).map((e) => [e.level, e.text])).toEqual([
      [2, "Two"],
      [3, "Three"],
      [4, "Four"],
    ]);
  });
});

describe("nestToc", () => {
  it("nests a sub-heading under the section above it", () => {
    const nodes = nestToc([
      { id: "a", text: "A", level: 2 },
      { id: "b", text: "B", level: 3 },
      { id: "c", text: "C", level: 2 },
    ]);
    expect(nodes.map((n) => n.id)).toEqual(["a", "c"]);
    expect(nodes[0].children.map((n) => n.id)).toEqual(["b"]);
    expect(nodes[1].children).toEqual([]);
  });

  // An h2 followed by an h4 is legal markdown. Dropping the orphan would put a
  // link in the page that appears in no rail.
  it("attaches a level jump rather than dropping the orphan", () => {
    const nodes = nestToc([
      { id: "a", text: "A", level: 2 },
      { id: "b", text: "B", level: 4 },
    ]);
    expect(nodes).toHaveLength(1);
    expect(nodes[0].children[0].id).toBe("b");
  });

  it("CONTROL: a flat list of siblings nests flat", () => {
    const nodes = nestToc([
      { id: "a", text: "A", level: 2 },
      { id: "b", text: "B", level: 2 },
    ]);
    expect(nodes.map((n) => n.id)).toEqual(["a", "b"]);
  });

  // Carries no page number on purpose: a page number is only knowable after
  // Paged.js paginates, and a number invented here is wrong until it is
  // rewritten in the print step.
  it("carries no page field for the print step to fill in", () => {
    const node = nestToc([{ id: "a", text: "A", level: 2 }])[0];
    expect(Object.keys(node).sort()).toEqual(["children", "id", "level", "text"]);
  });
});

describe("orderChapters", () => {
  it("sorts by order, then by slug so the spine never depends on the filesystem", () => {
    const sorted = orderChapters([REF("z-first", 2), REF("a-tie", 1), REF("b-tie", 1)]);
    expect(sorted.map((c) => c.slug)).toEqual(["a-tie", "b-tie", "z-first"]);
  });
});

describe("chapterNeighbours", () => {
  it("returns the surrounding chapters in book order", () => {
    const chapters = orderChapters([REF("one", 1), REF("two", 2), REF("three", 3)]);
    expect(chapterNeighbours(chapters, "two")).toEqual({
      previous: expect.objectContaining({ slug: "one" }),
      next: expect.objectContaining({ slug: "three" }),
    });
  });

  it("returns null at both ends, so the nav renders no dead link", () => {
    const chapters = orderChapters([REF("one", 1), REF("two", 2)]);
    expect(chapterNeighbours(chapters, "one").previous).toBeNull();
    expect(chapterNeighbours(chapters, "two").next).toBeNull();
  });

  it("returns nulls for a slug that is not in the book", () => {
    expect(chapterNeighbours(orderChapters([REF("one", 1)]), "nope")).toEqual({
      previous: null,
      next: null,
    });
  });
});
describe("sectionNeighbours", () => {
  const s = (chapter: string, slug: string, order: number) => ({
    chapter, slug, order, title: slug, summary: "", href: `/book/${chapter}/${slug}/`,
  });
  const ch = (slug: string, order: number, sections: ReturnType<typeof s>[]) => ({
    slug, order, title: slug, summary: "", href: `/book/${slug}/`, headingCount: sections.length, sections,
  });
  const book = [ch("02-b", 2, [s("02-b", "y", 2), s("02-b", "x", 1)]), ch("01-a", 1, [s("01-a", "p", 1), s("01-a", "q", 2)])];

  it("walks reading order across chapter boundaries", () => {
    expect(readingOrder(book).map((x) => x.slug)).toEqual(["p", "q", "x", "y"]);
    const mid = sectionNeighbours(book, "01-a", "q");
    expect(mid.previous?.slug).toBe("p");
    expect(mid.next?.slug).toBe("x");
  });

  it("returns null at either end", () => {
    expect(sectionNeighbours(book, "01-a", "p").previous).toBeNull();
    expect(sectionNeighbours(book, "02-b", "y").next).toBeNull();
  });
});
