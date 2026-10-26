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

import { startBouncingMark } from "@/lib/book/bounce-mark";
import { createPortal } from "react-dom";

import BookExportBar from "@/components/book/BookExportBar";
import { BOOK_PAGE_HEIGHT as PAGE_HEIGHT, BOOK_PAGE_WIDTH as PAGE_WIDTH } from "@/lib/book/readerCss";

/** A4 at 96dpi — the width the page boxes are laid out at. */

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
  const mark = useRef<HTMLCanvasElement>(null);
  const [active, setActive] = useState(chapters[0]?.page ?? 0);
  const [open, setOpen] = useState(false);
  const [scale, setScale] = useState(1);
  const [host, setHost] = useState<HTMLElement | null>(null);
  // Where each chapter actually starts once paginated. The server sends the
  // printed edition's map, which is right for the PDF but can be a page off
  // here: the book's gutters come from a viewport token, so a narrow window
  // breaks the last lines differently. Reading the chart off the page boxes
  // keeps the contents honest about the pages on screen.
  const [starts, setStarts] = useState<number[]>([]);
  const [liveHeight, setLiveHeight] = useState(0);
  // The pages take a moment to paginate. Until they are in the stage the reader
  // shows page-shaped placeholders at the exact size, so nothing moves when the
  // real thing arrives.
  const [ready, setReady] = useState(false);
  const settle = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  // The breathing mark that fills the wait: one page, one logo, bouncing. It
  // stops as soon as the pages are in, and holds still for a reader who asked
  // for reduced motion.
  useEffect(() => {
    if (!mark.current || ready) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    return startBouncingMark(mark.current, {
      width: PAGE_WIDTH,
      height: PAGE_HEIGHT,
      size: 240,
      speed: 105,
      still: reduced,
    });
  }, [ready]);

  // The layout sets the page light before paint; this only puts the reader's
  // own choice back when they leave the book.
  useEffect(() => {
    const html = document.documentElement;
    return () => {
      try {
        const theme = localStorage.getItem("dt-theme");
        const palette = localStorage.getItem("dt-palette");
        if (theme) html.setAttribute("data-theme", theme);
        else html.setAttribute("data-theme", "dark");
        if (palette) html.setAttribute("data-palette", palette);
        else html.removeAttribute("data-palette");
      } catch {
        /* storage blocked: leave the page as it is */
      }
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
      // The boxes arrive in a stream. Waiting for the count to settle is what
      // keeps a reader from watching one page become nineteen; the map's count
      // is a hint, not a fact, because a narrow window paginates one page short.
      if (pages && stage.current?.contains(pages)) {
        if (settle.current) clearTimeout(settle.current);
        settle.current = setTimeout(() => setReady(true), 320);
      }

      // pagedjs clones the source wrapper with the content, so a page box can
      // arrive holding a copy of the portal host — and with it the inline style
      // that parks the source off-screen. A page whose body sits inside that
      // wrapper is a blank sheet: the words are there, ten thousand pixels to
      // the left. Drop the empty copies, unwrap the ones that carry a page.
      document.querySelectorAll<HTMLElement>(".pagedjs_page .book-live__source").forEach((node) => {
        if (!(node.textContent ?? "").trim()) {
          node.remove();
          return;
        }
        node.removeAttribute("style");
        const parent = node.parentNode;
        while (node.firstChild) parent?.insertBefore(node.firstChild, node);
        node.remove();
      });

      // Where each chapter starts, read from the page boxes rather than from the
      // printed edition's map: the book's gutters come from a viewport token, so
      // a narrow window can break the last lines differently by a page.
      const marks = document.querySelectorAll<HTMLElement>(".pagedjs_page [data-book-anchor]");
      if (marks.length) {
        // Anchors arrive in reading order, one per chapter, which is the order
        // the contents is in. Index them rather than matching hrefs against
        // slugs: the anchor carries an href and the list carries a slug.
        const next: number[] = [];
        const seen = new Set<string>();
        for (const node of marks) {
          const anchor = node.dataset.bookAnchor ?? "";
          if (seen.has(anchor)) continue;
          seen.add(anchor);
          const page = node.closest<HTMLElement>(".pagedjs_page")?.dataset.bookPage;
          if (page) next.push(Number(page));
        }
        setStarts(next);
        const height = stage.current?.querySelector<HTMLElement>(".pagedjs_pages")?.clientHeight;
        if (height) setLiveHeight(height);
      }
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

  /** Where this chapter starts in the pagination on screen. */
  const startOf = (chapter: ReaderChapter, index: number) => starts[index] ?? chapter.page;

  // The chapter under the reading position, for the bar's own label: the last
  // one that starts at or before the page on screen.
  const current = chapters.reduce<{ chapter: ReaderChapter; index: number }>(
    (found, chapter, index) =>
      startOf(chapter, index) <= active ? { chapter, index } : found,
    { chapter: chapters[0], index: 0 },
  );

  const goTo = (page: number) => {
    setOpen(false);
    const box = document.querySelector<HTMLElement>(`[data-book-page="${page}"]`);
    if (!box) return;
    const top = box.getBoundingClientRect().top + window.scrollY - 96;
    window.scrollTo({ top, behavior: "smooth" });
  };

  return (
    <>
      <div className="book-shell">
        <nav className="book-nav" aria-label="Contents" data-open={open}>
          <button
            type="button"
            className="book-nav__toggle"
            aria-expanded={open}
            aria-label={open ? "hide contents" : "contents"}
            onClick={() => setOpen((value) => !value)}
          >
            <span className="book-nav__toggle-num">
              {String(current.chapter?.order ?? 1).padStart(2, "0")}
            </span>
            <span className="book-nav__toggle-text">{current.chapter?.title ?? "contents"}</span>
            <svg className="book-nav__chevron" viewBox="0 0 12 12" aria-hidden>
              <path d="M2 4.5 6 8l4-3.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
            </svg>
          </button>
          <p className="book-nav__title">contents</p>
          <ol>
            {chapters.map((chapter, index) => (
              <li key={chapter.slug}>
                <a
                  href={`#book-page-${startOf(chapter, index)}`}
                  aria-current={startOf(chapter, index) === active ? "true" : undefined}
                  onClick={(event) => {
                    event.preventDefault();
                    goTo(startOf(chapter, index));
                  }}
                >
                  <span className="book-nav__num">
                    {String(chapter.order).padStart(2, "0")}
                  </span>
                  <span>{chapter.title}</span>
                  <span className="book-nav__page">{startOf(chapter, index)}</span>
                </a>
              </li>
            ))}
          </ol>
          {/* Built in the reader's own theme and palette, because one static
              file cannot be every theme's PDF. */}
          <BookExportBar />
        </nav>

        <div
          className="book-live"
          ref={frame}
          data-ready={ready ? "true" : undefined}
          style={{ height: (liveHeight || pageCount * PAGE_HEIGHT) * scale }}
        >
          <div
            className="book-live__stage"
            ref={stage}
            style={{ width: PAGE_WIDTH, transform: `scale(${scale})` }}
          >
            <div className="book-live__skeleton" data-ready={ready ? "true" : undefined}>
              {/* One placeholder, where page one will land. The rest of the book
                  arrives behind it; there is nothing to mark further down. */}
              <canvas
                ref={mark}
                className="book-live__mark"
                aria-hidden
                width={PAGE_WIDTH}
                height={PAGE_HEIGHT}
              />
            </div>
          </div>
          {/* The document paginates in the body-level host and the finished
              page boxes are moved into the stage above. */}
          {host ? createPortal(children, host) : null}
        </div>
      </div>
    </>
  );
}
