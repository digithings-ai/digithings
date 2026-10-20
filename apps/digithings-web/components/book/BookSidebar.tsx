import Link from "next/link";

import type { ChapterWithSections } from "@/lib/book/toc";

/**
 * The book's table of contents as a sidebar: chapters with their sections
 * nested, the current page highlighted, every page one click away. Server
 * component — the page knows where it is, so no client script is needed.
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
    <nav aria-label="Book contents" className="font-mono text-[0.78rem] leading-[1.45]">
      <Link href="/book/" className="text-ink-soft">
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
                className={chapterActive ? "text-ink" : "text-ink-soft"}
              >
                <span className="text-ink-soft">{String(c.order).padStart(2, "0")}</span> {c.title}
              </Link>
              <ol className="mt-1 list-none border-hair border-l p-0 pl-3">
                {c.sections.map((s) => {
                  const active = chapterActive && s.slug === section;
                  return (
                    <li key={s.slug} className="py-0.5">
                      <Link
                        href={s.href}
                        aria-current={active ? "page" : undefined}
                        className={active ? "text-ink" : "text-ink-soft"}
                      >
                        {active ? "▸ " : ""}
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
