"use client";

/**
 * The shell around the paginated book at `/book`: contents on the left, the
 * book's pages on the right, scrolling like the docs.
 *
 * The pages themselves are the PDF's own pages, rendered as images by the
 * server component. That is deliberate — a live re-pagination in the browser
 * reflowed with the window (19 pages at 1280px, 20 at 1440), so the numbers in
 * this sidebar stopped agreeing with the paper. The PDF is the fixed artefact;
 * this page shows it.
 *
 * The numbers are generated, not typed: `lib/book/generated/pages.json` is read
 * off the same pagination `scripts/book/print-pdf.mjs` prints from.
 */
import { useEffect, useState } from "react";

import { BOOK_READER_CSS } from "@/lib/book/readerCss";

export type ReaderChapter = {
  slug: string;
  title: string;
  /** Printed chapter number, already sequential over the brief. */
  order: number;
  /** First page of the chapter in the PDF, 1-based. */
  page: number;
};

export default function BookPages({
  chapters,
  children,
}: {
  chapters: readonly ReaderChapter[];
  children: React.ReactNode;
}) {
  const [active, setActive] = useState(chapters[0]?.page ?? 0);
  const [open, setOpen] = useState(false);

  // Which page the reader is looking at, for the contents highlight. The pages
  // are plain figures, so the position of the boxes is all the state there is.
  useEffect(() => {
    const onScroll = () => {
      const line = 140;
      let page = chapters[0]?.page ?? 0;
      for (const sheet of document.querySelectorAll<HTMLElement>("[data-book-page]")) {
        if (sheet.getBoundingClientRect().top <= line) page = Number(sheet.dataset.bookPage);
      }
      setActive(page);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [chapters]);

  // A page printed from here is the book, so every page has to be in the
  // document before the print dialog takes its snapshot: images below the fold
  // are lazy, and a lazy image prints as an empty sheet.
  useEffect(() => {
    const loadAll = () => {
      document
        .querySelectorAll<HTMLImageElement>(".book-frames__page")
        .forEach((image) => {
          image.loading = "eager";
        });
    };
    window.addEventListener("beforeprint", loadAll);
    return () => window.removeEventListener("beforeprint", loadAll);
  }, []);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: BOOK_READER_CSS }} />
      <div className="book-shell">
        <nav className="book-nav" aria-label="Contents" data-open={open}>
          <button
            type="button"
            className="book-nav__toggle"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? "hide contents" : "contents"}
          </button>
          <p className="book-nav__title">contents</p>
          <ol>
            {chapters.map((chapter) => (
              <li key={chapter.slug}>
                <a
                  href={`#book-page-${chapter.page}`}
                  aria-current={chapter.page === active ? "true" : undefined}
                  onClick={() => setOpen(false)}
                >
                  <span className="book-nav__num">
                    {String(chapter.order).padStart(2, "0")}
                  </span>
                  <span>{chapter.title}</span>
                  <span className="book-nav__page">{chapter.page}</span>
                </a>
              </li>
            ))}
          </ol>
          <a className="book-nav__download" href="/book/the-digithings-book.pdf" download>
            download the pdf
          </a>
        </nav>

        <div className="book-frames">
          {children}
        </div>
      </div>
    </>
  );
}
