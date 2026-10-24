import type { ReactNode } from "react";

import BookSidebar from "./BookSidebar";
import ChapterRail from "./ChapterRail";
import SectionNav from "./SectionNav";
import type { ChapterWithSections, SectionRef, TocEntry } from "@/lib/book/toc";

/** The three-column book page: contents sidebar, the page, "on this page". */
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
  chapterTitle,
  children,
}: {
  chapters: readonly ChapterWithSections[];
  chapter: string;
  section?: string;
  chapterTitle?: string;
  kicker: string;
  title: string;
  summary: string;
  toc: readonly TocEntry[];
  previous: SectionRef | null;
  next: SectionRef | null;
  children: ReactNode;
}) {
  return (
    <div className="pt-[clamp(2rem,5vw,3.5rem)]">
      {/* Below lg the two rails have nowhere to sit, so the same contents and
          heading list become one disclosure instead of disappearing. */}
      <details className="book-screen-only group mb-8 border-hair border-b pb-4 lg:hidden">
        <summary className="flex min-h-11 list-none items-center justify-between gap-4 font-mono text-[0.8rem] text-ink-soft [&::-webkit-details-marker]:hidden">
          <span>
            contents
            {chapterTitle ? <span className="text-ink"> · {chapterTitle}</span> : null}
          </span>
          <span aria-hidden="true" className="text-accent">
            <span className="group-open:hidden">open</span>
            <span className="hidden group-open:inline">close</span>
          </span>
        </summary>
        <div className="mt-4 grid gap-6 sm:grid-cols-2">
          <BookSidebar chapters={chapters} chapter={chapter} section={section} />
          <ChapterRail entries={toc} />
        </div>
      </details>

      <div className="grid gap-10 lg:grid-cols-[15rem_minmax(0,1fr)_12rem]">
        <aside className="book-screen-only hidden lg:sticky lg:top-[calc(var(--dq-nav-h)+1.5rem)] lg:block lg:max-h-[calc(100vh-var(--dq-nav-h)-3rem)] lg:self-start lg:overflow-y-auto">
          <BookSidebar chapters={chapters} chapter={chapter} section={section} />
        </aside>
        <article className="book-chapter min-w-0">
          <p className="m-0 font-mono text-[0.8rem] text-ink-soft">{kicker}</p>
          <h1 className="mb-2 font-display text-[clamp(1.9rem,3.6vw,2.6rem)] leading-[1.08] tracking-[-0.02em] text-ink">
            {title}
          </h1>
          <p className="mb-8 max-w-[64ch] text-[1.05rem] leading-[1.7] text-ink-soft">{summary}</p>
          {children}
          <SectionNav previous={previous} next={next} />
        </article>
        <aside className="book-screen-only hidden lg:sticky lg:top-[calc(var(--dq-nav-h)+1.5rem)] lg:block lg:self-start">
          <ChapterRail entries={toc} />
        </aside>
      </div>
    </div>
  );
}
