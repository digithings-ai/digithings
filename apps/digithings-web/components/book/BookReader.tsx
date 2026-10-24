"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { isTypingTarget, pageDelta, stepPage, type ReaderPage } from "@/lib/book/reader";

/**
 * The web edition's reading frame: the PDF's page sequence as a scroll of
 * sheets, with the contents in a sidebar.
 *
 * The sheets are server-rendered children; this component only adds the
 * navigation. Scrolling moves through the pages as it would through a PDF
 * viewer, the left and right arrows turn one page, and the sidebar and the
 * page counter follow whichever sheet holds the middle of the viewport.
 */
export default function BookReader({
  pages,
  children,
}: {
  pages: readonly ReaderPage[];
  children: ReactNode;
}) {
  const [current, setCurrent] = useState(pages[0]?.id ?? "");

  const go = useCallback((id: string) => {
    const sheet = document.getElementById(id);
    if (!sheet) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    sheet.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    sheet.focus({ preventScroll: true });
    setCurrent(id);
    window.history.replaceState(null, "", `#${id}`);
  }, []);

  // The sheet crossing the middle of the viewport is the page being read.
  useEffect(() => {
    const sheets = pages
      .map((page) => document.getElementById(page.id))
      .filter((sheet): sheet is HTMLElement => sheet !== null);
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          setCurrent(entry.target.id);
          window.history.replaceState(null, "", `#${entry.target.id}`);
        }
      },
      { rootMargin: "-45% 0px -54% 0px" },
    );
    sheets.forEach((sheet) => observer.observe(sheet));
    return () => observer.disconnect();
  }, [pages]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || isTypingTarget(event.target)) return;
      const delta = pageDelta(event);
      if (delta === 0) return;
      const target = stepPage(pages, current, delta);
      if (!target || target.id === current) return;
      event.preventDefault();
      go(target.id);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pages, current, go]);

  const index = Math.max(
    0,
    pages.findIndex((page) => page.id === current),
  );
  const previous = index > 0 ? pages[index - 1] : null;
  const next = index < pages.length - 1 ? pages[index + 1] : null;
  const link = (page: ReaderPage) => (
    <a
      href={`#${page.id}`}
      aria-current={page.id === current ? "page" : undefined}
      onClick={(event) => {
        event.preventDefault();
        go(page.id);
      }}
      className={`flex min-h-9 items-baseline gap-2 py-1 hover:text-ink ${page.id === current ? "text-ink" : "text-ink-soft"}`}
    >
      <span className="w-5 shrink-0 text-accent">{page.number}</span>
      <span>{page.title}</span>
    </a>
  );

  const contents = (
    <nav aria-label="Book contents" className="font-mono text-[0.78rem] leading-[1.45]">
      <ol className="m-0 list-none p-0">
        {pages.map((page) => (
          <li key={page.id} className="border-hair border-b last:border-b-0">
            {link(page)}
          </li>
        ))}
      </ol>
    </nav>
  );

  return (
    <div className="pt-[clamp(2rem,5vw,3.5rem)]">
      <details className="book-screen-only group mb-6 border-hair border-b pb-4 lg:hidden">
        <summary className="flex min-h-11 list-none items-center justify-between gap-4 font-mono text-[0.8rem] text-ink-soft [&::-webkit-details-marker]:hidden">
          <span>
            contents <span className="text-ink">· {pages[index]?.title}</span>
          </span>
          <span aria-hidden="true" className="text-accent">
            <span className="group-open:hidden">open</span>
            <span className="hidden group-open:inline">close</span>
          </span>
        </summary>
        <div className="mt-4">{contents}</div>
      </details>

      <div className="grid gap-10 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="book-screen-only hidden lg:sticky lg:top-[calc(var(--dq-nav-h)+1.5rem)] lg:block lg:max-h-[calc(100vh-var(--dq-nav-h)-3rem)] lg:self-start lg:overflow-y-auto">
          {contents}
          <p className="mt-6 font-mono text-[0.72rem] text-ink-soft">← → turn the page</p>
        </aside>
        <div className="min-w-0">
          {children}
          <nav
            aria-label="Pages"
            className="book-screen-only sticky bottom-0 z-10 flex items-center justify-between gap-4 border-hair border-t bg-[var(--bg)] py-3 font-mono text-[0.8rem]"
          >
            <button
              type="button"
              disabled={!previous}
              onClick={() => previous && go(previous.id)}
              className="min-h-11 px-2 text-ink-soft hover:text-ink disabled:opacity-40"
            >
              ← previous
            </button>
            <span className="text-ink-soft" aria-live="polite">
              {index + 1} / {pages.length}
            </span>
            <button
              type="button"
              disabled={!next}
              onClick={() => next && go(next.id)}
              className="min-h-11 px-2 text-ink-soft hover:text-ink disabled:opacity-40"
            >
              next →
            </button>
          </nav>
        </div>
      </div>
    </div>
  );
}
