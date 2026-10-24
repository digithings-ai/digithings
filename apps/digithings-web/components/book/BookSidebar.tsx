import Link from "next/link";

import type { ChapterWithSections } from "@/lib/book/toc";

/**
 * The book's table of contents as a sidebar (DIG-2821, U17): chapters with
 * their sections nested, the current page marked, every page one click away.
 * Server component — the page knows where it is, so no client script is needed.
 *
 * The current entry is marked twice: `aria-current="page"` for assistive
 * technology, and a 1px accent tick on the hairline the list already draws
 * (`.book-sidebar li[data-active]`, lib/book/printCss.ts) so the mark survives
 * print and does not depend on colour alone.
 */
export default function BookSidebar({
  chapters,
  chapter,
  section,
}: {
  chapters: readonly ChapterWithSections[];
  chapter?: string;
  section?: string;
}) {
  return (
    <nav aria-label="Book contents" className="book-sidebar font-mono text-[0.78rem] leading-[1.45]">
      <Link href="/book/" className="text-ink-soft hover:text-ink">
        the digithings book
      </Link>
      <ol className="mt-4 list-none p-0">
        {chapters.map((c) => {
          const chapterActive = c.slug === chapter;
          const openerActive = chapterActive && !section;
          return (
            <li key={c.slug} className="mb-3">
              <Link
                href={c.href}
                aria-current={openerActive ? "page" : undefined}
                className={chapterActive ? "text-ink" : "text-ink-soft hover:text-ink"}
              >
                <span className="text-ink-soft">{String(c.order).padStart(2, "0")}</span> {c.title}
              </Link>
              <ol className="mt-1 list-none border-hair border-l p-0 pl-3">
                {c.sections.map((s) => {
                  const active = chapterActive && s.slug === section;
                  return (
                    <li key={s.slug} className="py-0.5" data-active={active || undefined}>
                      <Link
                        href={s.href}
                        aria-current={active ? "page" : undefined}
                        className={active ? "text-ink" : "text-ink-soft hover:text-ink"}
                      >
                        {s.title}
                      </Link>
                    </li>
                  );
                })}
              </ol>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
