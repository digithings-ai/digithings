import type { Metadata } from "next";

import BookToc from "@/components/book/BookToc";
import PagedBoot from "@/components/book/PagedBoot";
import { briefChapters } from "@/lib/book/brief";
import { WORDMARK } from "@/lib/book/wordmark";
import { chapterRefs, loadChapters } from "@/lib/book/chapters.server";

/**
 * The print artefact is a rendering of the same book content with PagedJS
 * chrome; it is not a destination page. Keep it out of the index (searchers
 * want /book, which is where we send them instead).
 */
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

/**
 * The whole book as one continuous document — the thing that gets printed
 * (DIG-2821).
 *
 * Why one page and not "print each chapter": the printed book needs running
 * headers that change per chapter, page numbers that are continuous across the
 * volume, and a front table of contents whose page references were resolved
 * from the SAME pagination that produced those numbers. Splitting the print
 * into per-chapter pages gives three separate documents, and a page reference
 * in one of them means nothing to the reader holding a different one.
 */
export default async function BookPrintPage() {
  // The PDF is the brief edition (lib/book/brief.ts): the chapters that carry
  // the argument for a client or partner, in editorial order. The web keeps
  // every chapter; paper keeps the through-line and fits in half an hour.
  const chapters = briefChapters(loadChapters(process.cwd()));
  // Print numbering is sequential over the chapters that actually ship. The
  // source `order` values skip drafts (03, 06–09), which made a book whose
  // contents read 01, 02, 04, 05, 10.
  // `chapterRefs` sorts by source `order:`; the contents must follow the brief.
  const refs = briefChapters(chapterRefs(chapters)).map((chapter, index) => ({
    ...chapter,
    order: index + 1,
  }));

  // Loaded up front, before any JSX: a page that will not compile must fail
  // the build, not leave a hole in the printed book. Every chapter opener and
  // every section, in reading order — the web splits them into pages, paper
  // flows them continuously.
  const bodies = await Promise.all(
    chapters.map(async (chapter) => {
      const load = async (file: string) =>
        (
          (await import(`../../../content/book/${chapter.slug}/${file}.mdx`)) as {
            default: () => React.JSX.Element;
          }
        ).default;
      return { chapter, Opener: await load("index") };
    }),
  );

  return (
    // `data-paged-content` is what PagedBoot hands the chunker: this element
    // becomes the paginated document. The site nav and footer sit outside it,
    // and so does PagedBoot's status line, so it can never be paginated.
    <>
      <PagedBoot enabled />
      <div
        data-paged-content="book"
        className="book-flow mx-auto w-full max-w-[var(--wrap)] px-[var(--gutter)]"
      >
        <div className="book-print-only running-element">
          <span>the digithings book</span>
          <span>digithings.ai/book</span>
        </div>

        <section className="book-cover">
          <div
            className="book-cover__mark"
            aria-hidden
            dangerouslySetInnerHTML={{ __html: WORDMARK }}
          />
          <div className="book-cover__foot">
            <h1 className="book-cover__title">the digithings book</h1>
          </div>
          <p className="book-cover__imprint">edition 26 · version 1</p>
        </section>

        {/* Front matter. The reference beside each chapter is filled in by
          PagedBoot, after the engine has decided where the pages break — a
          number written here would be wrong the moment a paragraph grew a
          line. */}
        <section className="book-contents">
          <h2 className="book-contents__title">contents</h2>
          <BookToc chapters={refs} withRefs />
        </section>

        {bodies.map(({ chapter, Opener }, index) => {
          const displayOrder = index + 1;
          return (
            <section key={chapter.slug} className="book-chapter">
              {/* Anchors the front matter's page references resolve against. */}
              <div data-book-anchor={chapter.href} />
              <div className="book-chapter__head">
                <p className="m-0 font-mono text-[0.8rem] text-accent">
                  {String(displayOrder).padStart(2, "0")}
                </p>
                {/* The book title above is the page's single h1; chapter openers
                sit one level below it so the printed outline stays in order. */}
                <h2 className="mb-2 font-display text-[1.8rem] tracking-[-0.02em] text-ink">
                  {chapter.title}
                </h2>
              </div>
              <Opener />
            </section>
          );
        })}

        <section className="book-colophon">
          <div
            className="book-colophon__mark"
            aria-hidden
            dangerouslySetInnerHTML={{ __html: WORDMARK }}
          />
          <div className="book-colophon__foot">
            <p className="book-colophon__kicker">the digithings book</p>
            <p className="book-colophon__title">edition 2026 · version 1.0</p>
          </div>
        </section>
      </div>
    </>
  );
}

export const dynamic = "force-static";
