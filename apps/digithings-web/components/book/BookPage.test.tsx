import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import BookPage from "./BookPage";
import type { ChapterWithSections, SectionRef } from "@/lib/book/toc";

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

const previous: SectionRef = {
  chapter: "why",
  slug: "start",
  title: "Start here",
  summary: "What the book is for.",
  order: 1,
  href: "/book/why/start/",
};

const next: SectionRef = {
  chapter: "why",
  slug: "next",
  title: "How it scales",
  summary: "What happens as the stack grows.",
  order: 2,
  href: "/book/why/next/",
};

function render() {
  return renderToStaticMarkup(
    <BookPage
      chapters={chapters}
      chapter="why"
      section="start"
      chapterTitle="Why this book exists"
      kicker="01.1 · Why this book exists"
      title="Start here"
      summary="What the book is for."
      toc={[{ id: "the-argument", text: "The argument", level: 2 }]}
      previous={previous}
      next={next}
    >
      <p>Body</p>
    </BookPage>,
  );
}

describe("BookPage", () => {
  it("gives narrow screens a real contents disclosure", () => {
    const html = render();
    expect(html).toContain("<details");
    expect(html).toContain("lg:hidden");
    expect(html).toContain("contents");
    expect(html).toContain("Why this book exists");
    expect((html.match(/aria-label="Book contents"/g) ?? []).length).toBeGreaterThanOrEqual(1);
    expect(html).toContain('aria-label="On this page"');
  });

  it("stacks prev/next instead of shrinking them into two narrow columns", () => {
    const html = render();
    expect(html).toContain('aria-label="Sections"');
    expect(html).toContain("grid-cols-1");
    expect(html).toContain("sm:grid-cols-2");
    expect(html).not.toContain("max-w-[48%]");
    expect(html).toContain('rel="prev"');
    expect(html).toContain('rel="next"');
    expect(html).toContain("How it scales");
  });
});
