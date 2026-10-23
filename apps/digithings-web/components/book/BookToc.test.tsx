import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import BookToc from "./BookToc";
import type { ChapterWithSections } from "@/lib/book/toc";

const chapters: ChapterWithSections[] = [
  {
    slug: "why",
    title: "Why this book exists",
    summary: "The argument for owning the stack.",
    order: 1,
    href: "/book/why/",
    headingCount: 2,
    sections: [
      {
        chapter: "why",
        slug: "start",
        title: "Start here",
        summary: "What the book is for.",
        order: 1,
        href: "/book/why/start/",
      },
    ],
  },
];

describe("BookToc", () => {
  it("gives every print entry a dot leader and a page-reference cell", () => {
    const html = renderToStaticMarkup(<BookToc chapters={chapters} withRefs />);
    expect(html.match(/book-toc__leader/g) ?? []).toHaveLength(2);
    expect(html).toContain('data-book-toc-ref="/book/why/"');
    expect(html).toContain('data-book-toc-ref="/book/why/start/"');
  });

  it("does not reserve page references on the screen index", () => {
    const html = renderToStaticMarkup(<BookToc chapters={chapters} />);
    expect(html).not.toContain("book-toc__leader");
    expect(html).not.toContain("data-book-toc-ref");
  });
});
