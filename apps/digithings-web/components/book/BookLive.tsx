"use client";

/**
 * The book on screen, at `/book`: the same paginated document the PDF is
 * printed from, scaled to the column and scrolled in the page.
 *
 * It is not a second rendering. The site's tokens are on `<html>`, pagedjs
 * copies them into every page box, so the book follows the reader's theme and
 * palette — all of them, not just light and dark — with no colour written
 * anywhere in the book. A theme change repaints it live.
 *
 * The document paginates at a fixed A4 width whoever is looking: page boxes are
 * sized from `@page`, not from the window (measured: 19 pages at 794, 1024,
 * 1280 and 1440 px), which is why the numbers here can be the printed numbers.
 */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import BookDownloadButton from "@/components/book/BookDownloadButton";
import { BOOK_READER_CSS } from "@/lib/book/readerCss";

/** A4 at 96dpi — the width the page boxes are laid out at. */
const PAGE_WIDTH = 794;
const PAGE_HEIGHT = 1123;

export type ReaderChapter = {
  slug: string;
  title: string;
  /** Printed chapter number, already sequential over the brief. */
  order: number;
  /** First page of the chapter in the printed edition, 1-based. */
  page: number;
};

export default function BookLive({
  chapters,
  pageCount,
  children,
}: {
  chapters: readonly ReaderChapter[];
  pageCount: number;
  children: React.ReactNode;
}) {
  const stage = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(chapters[0]?.page ?? 0);
  const [open, setOpen] = useState(false);
  const [scale, setScale] = useState(1);
  const [host, setHost] = useState<HTMLElement | null>(null);

  // The document is paginated outside the reader's own markup. pagedjs reflows
  // what it is handed, and a document nested in the shell was reflowed with its
  // wrappers: the page boxes came back holding copies of the reader. A host on
  // <body> keeps the source out of that tree; the finished pages are moved back
  // into the stage below.
  useEffect(() => {
    const element = document.createElement("div");
    element.className = "book-live__source";
    document.body.appendChild(element);
    setHost(element);
    return () => {
      setHost(null);
      element.remove();
    };
  }, []);

  // Fit the fixed-width pages into the column. The stage keeps its natural A4
  // width and is scaled visually, so the layout — and therefore the pagination
  // and the page numbers — never depend on the window.
  useEffect(() => {
    const fit = () => {
      const width = frame.current?.clientWidth ?? PAGE_WIDTH;
      setScale(Math.min(1, width / PAGE_WIDTH));
    };
    fit();
    const observer = new ResizeObserver(fit);
    if (frame.current) observer.observe(frame.current);
    return () => observer.disconnect();
  }, []);

  // pagedjs appends the page boxes to <html>, not to the element it was given.
  // Move them into the stage once the pagination marker appears, so they take
  // the column's place instead of landing after the footer.
  useEffect(() => {
    const take = () => {
      const pages = document.querySelector<HTMLElement>(".pagedjs_pages");
      if (pages && stage.current && pages.parentElement !== stage.current) {
        stage.current.appendChild(pages);
      }
      // pagedjs clones the source wrapper with the content, so page boxes keep
      // arriving with a copy of the portal host inside them. They are empty and
      // out of flow, but they would accumulate for the life of the page.
      document
        .querySelectorAll(".pagedjs_page .book-live__source")
        .forEach((node) => node.remove());
    };
    take();
    const observer = new MutationObserver(take);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  // Which page the reader is looking at, for the contents highlight.
  useEffect(() => {
    const onScroll = () => {
      const line = 140;
      let page = chapters[0]?.page ?? 0;
      for (const box of document.querySelectorAll<HTMLElement>("[data-book-page]")) {
        if (box.getBoundingClientRect().top <= line) page = Number(box.dataset.bookPage);
      }
      setActive(page);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [chapters]);

  const goTo = (page: number) => {
    setOpen(false);
    const box = document.querySelector<HTMLElement>(`[data-book-page="${page}"]`);
    if (!box) return;
    const top = box.getBoundingClientRect().top + window.scrollY - 96;
    window.scrollTo({ top, behavior: "smooth" });
  };

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
                  onClick={(event) => {
                    event.preventDefault();
                    goTo(chapter.page);
                  }}
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
          {/* Built in the reader's own theme and palette, because one static
              file cannot be every theme's PDF. */}
          <BookDownloadButton className="book-nav__download" />
        </nav>

        <div
          className="book-live"
          ref={frame}
          style={{ height: pageCount * PAGE_HEIGHT * scale }}
        >
          <div
            className="book-live__stage"
            ref={stage}
            style={{ width: PAGE_WIDTH, transform: `scale(${scale})` }}
          />
          {/* The document paginates in the body-level host and the finished
              page boxes are moved into the stage above. */}
          {host ? createPortal(children, host) : null}
        </div>
      </div>
    </>
  );
}
