import type { ReactNode } from "react";

import BookSidebar from "./BookSidebar";
import ChapterRail from "./ChapterRail";
import SectionNav from "./SectionNav";
import type { ChapterWithSections, SectionRef, TocEntry } from "@/lib/book/toc";

/**
 * The three-column book page (DIG-2821, U17): contents sidebar, the page,
 * "on this page".
 *
 * On a phone the sidebar is not a column, it is a wall of links above the
 * chapter, so below `lg` it collapses into a `<details>` at the top of the
 * article. `<details>` is the accordion: it opens without JavaScript, it is
 * keyboard-operable, and it announces its own state. The desktop aside is
 * hidden at that breakpoint, so there is one labelled contents nav in the
 * accessibility tree at a time.
 */
export default function BookPage({
  chapters,
  chapter,
  section,
  kicker,
  title,
  summary,
  toc,
  previous,
  next,
  children,
}: {
  chapters: readonly ChapterWithSections[];
  chapter: string;
  section?: string;
  kicker: string;
  title: string;
  summary: string;
  toc: readonly TocEntry[];
  previous: SectionRef | null;
  next: SectionRef | null;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-10 pt-[clamp(2rem,5vw,3.5rem)] lg:grid-cols-[15rem_minmax(0,1fr)_12rem]">
      <aside className="book-screen-only hidden lg:sticky lg:top-[calc(var(--dq-nav-h)+1.5rem)] lg:block lg:max-h-[calc(100vh-var(--dq-nav-h)-3rem)] lg:self-start lg:overflow-y-auto">
        <BookSidebar chapters={chapters} chapter={chapter} section={section} />
      </aside>
      <article className="book-chapter min-w-0">
        <details className="book-screen-only mb-8 border-hair border-b pb-3 lg:hidden">
          <summary className="font-mono text-[0.8rem] text-ink">contents</summary>
          <div className="mt-4">
            <BookSidebar chapters={chapters} chapter={chapter} section={section} />
          </div>
        </details>
        <p className="m-0 font-mono text-[0.75rem] text-ink-soft">{kicker}</p>
        <h1 className="mt-2 mb-3 text-balance font-display text-[clamp(1.9rem,3.6vw,2.6rem)] leading-[1.08] tracking-[-0.02em] text-ink">
          {title}
        </h1>
        <p className="mb-10 max-w-[var(--measure-prose)] text-[1.02rem] leading-[1.65] text-ink-soft">{summary}</p>
        {children}
        <SectionNav previous={previous} next={next} />
      </article>
      <aside className="book-screen-only hidden lg:sticky lg:top-[calc(var(--dq-nav-h)+1.5rem)] lg:block lg:self-start">
        <ChapterRail entries={toc} />
      </aside>
    </div>
  );
}
