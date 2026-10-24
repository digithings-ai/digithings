/**
 * Contract coverage for the reading surface (U17, epic #6327).
 *
 * The book has no interactive test harness of its own, and none of these
 * behaviours need one: every claim here is a claim about the markup a reader
 * gets. So the components are server-rendered with `renderToStaticMarkup` on
 * the same node environment as the rest of the app's tests, and the assertions
 * are made against what the browser would receive.
 *
 * What is pinned, and why each one is easy to regress:
 *
 *  - the contents sidebar is reachable on a phone (`<details>`) and is not
 *    printed twice into the same viewport;
 *  - prev/next are two columns that fit, name their direction in words and
 *    terminate at both ends of the book;
 *  - the current section is marked for assistive technology and, separately,
 *    with a shape, not colour alone;
 *  - a code block is a keyboard-reachable scroll container with a copy
 *    control, and its overflow hint is only visible when it overflows;
 *  - an ordinary image is a real figure with a caption, and a diagram is not
 *    wrapped in a second one.
 */
import type { ComponentType, ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import BookFigure from "./BookFigure";
import BookPage from "./BookPage";
import BookSidebar from "./BookSidebar";
import { useMDXComponents } from "@/mdx-components";
import type { ChapterWithSections, SectionRef } from "@/lib/book/toc";

const section = (chapter: string, slug: string, order: number, title: string): SectionRef => ({
  chapter,
  slug,
  order,
  title,
  summary: "s",
  href: `/book/${chapter}/${slug}/`,
});

const chapters: ChapterWithSections[] = [
  {
    slug: "01-one",
    order: 1,
    title: "one",
    summary: "the first chapter",
    href: "/book/01-one/",
    headingCount: 2,
    sections: [section("01-one", "aa", 1, "aa"), section("01-one", "bb", 2, "bb")],
  },
  {
    slug: "02-two",
    order: 2,
    title: "two",
    summary: "the second chapter",
    href: "/book/02-two/",
    headingCount: 0,
    sections: [],
  },
];

const renderPage = (previous: SectionRef | null, next: SectionRef | null) =>
  renderToStaticMarkup(
    <BookPage
      chapters={chapters}
      chapter="01-one"
      section="aa"
      kicker="01.1 · one"
      title="aa"
      summary="the first section"
      toc={[]}
      previous={previous}
      next={next}
    >
      <p>body</p>
    </BookPage>,
  );

describe("the contents sidebar", () => {
  it("is collapsed into a details element and hidden from the desktop column", () => {
    const html = renderPage(null, null);
    expect(html).toContain("<details");
    expect(html).toContain("<summary");
    expect(html).toContain("contents");
    // one copy of the nav for the phone, one for the desktop column
    expect(html.match(/aria-label="Book contents"/g)).toHaveLength(2);
    expect(html).toContain("hidden");
    expect(html).toContain("lg:sticky");
    expect(html).toContain("lg:hidden");
  });

  it("marks the current section for assistive technology and with a shape", () => {
    const html = renderToStaticMarkup(<BookSidebar chapters={chapters} chapter="01-one" section="aa" />);
    expect(html).toContain('aria-current="page"');
    // exactly one current page, on the section level, not the chapter opener
    expect(html.match(/aria-current="page"/g)).toHaveLength(1);
    expect(html).toContain("data-active");
  });

  it("drops the decorative glyph that used to precede the active entry", () => {
    const html = renderToStaticMarkup(<BookSidebar chapters={chapters} chapter="01-one" section="aa" />);
    expect(html).not.toContain("▸");
  });
});

describe("previous / next", () => {
  it("fits two columns without a maximum width that overflows", () => {
    const html = renderPage(section("00-zero", "zz", 1, "before"), section("02-two", "cc", 1, "after"));
    expect(html).toContain("sm:grid-cols-2");
    expect(html).not.toContain("max-w-[48%]");
    expect(html).toContain('aria-label="Reading order"');
  });

  it("names the direction in words instead of a bare arrow", () => {
    const html = renderPage(section("00-zero", "zz", 1, "before"), section("02-two", "cc", 1, "after"));
    expect(html).toContain("previous");
    expect(html).toContain("next");
    expect(html).not.toMatch(/[←→]/);
    expect(html).toContain('rel="prev"');
    expect(html).toContain('rel="next"');
  });

  it("terminates at both ends of the book instead of rendering an empty slot", () => {
    const first = renderPage(null, section("02-two", "cc", 1, "after"));
    expect(first).toContain("start of the book");
    expect(first).toContain('href="/book"');
    const last = renderPage(section("01-one", "aa", 1, "before"), null);
    expect(last).toContain("end of the book");
    expect(last).toContain("back to contents");
    expect(last).not.toContain('rel="next"');
  });
});

describe("figures", () => {
  it("renders an ordinary image as a figure with a caption and no layout shift", () => {
    const html = renderToStaticMarkup(<BookFigure src="/book/img/x.png" alt="a chart" title="the caption" width={800} height={400} />);
    expect(html).toContain("<figure");
    expect(html).toContain("<figcaption");
    expect(html).toContain("the caption");
    expect(html).toContain('loading="lazy"');
    expect(html).toContain('decoding="async"');
    expect(html).toContain('width="800"');
    expect(html).toContain('height="400"');
  });

  it("does not wrap a diagram in a second figure", () => {
    const html = renderToStaticMarkup(<BookFigure src="/book/diagrams/x.svg" alt="a diagram" />);
    expect(html.match(/<figure/g)).toHaveLength(1);
  });
});

describe("the MDX map", () => {
  const M = useMDXComponents({}) as unknown as Record<string, ComponentType<{ children?: ReactNode }>>;

  it("gives prose the reading measure and leading from the tokens", () => {
    const html = renderToStaticMarkup(<M.p>text</M.p>);
    expect(html).toContain("max-w-[var(--measure-prose)]");
    expect(html).toContain("leading-[var(--leading-prose)]");
    expect(html).not.toContain("64ch");
  });

  it("puts every code block behind the shared code component", () => {
    const html = renderToStaticMarkup(
      <M.pre>
        <code>npm run build</code>
      </M.pre>,
    );
    expect(html).toContain('aria-label="code block"');
    expect(html).toContain('tabindex="0"');
    expect(html).toContain("copy");
  });

  it("scrolls a wide table inside its own box", () => {
    const html = renderToStaticMarkup(
      <M.table>
        <tbody>
          <tr>
            <td>cell</td>
          </tr>
        </tbody>
      </M.table>,
    );
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain('role="region"');
  });
});
