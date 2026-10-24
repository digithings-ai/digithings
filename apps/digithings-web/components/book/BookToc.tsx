import Link from "next/link";

import type { ChapterWithSections } from "@/lib/book/toc";

/**
 * The book's table of contents (DIG-2821).
 *
 * Carries no page number. A page number is only knowable once Paged.js has
 * paginated the document, so this renders an empty `.book-toc__ref` cell that
 * the print step fills in (`components/book/PagedBoot.tsx`). On screen it stays
 * empty, which is honest — a web reader scrolls, and the heading rail already
 * tells them where they are.
 */
export default function BookToc({
  chapters,
  withRefs = false,
}: {
  chapters: readonly ChapterWithSections[];
  /** Print route only: reserve the column the page references land in. */
  withRefs?: boolean;
}) {
  if (chapters.length === 0) {
    return <p className="font-mono text-ink-soft">no chapters yet</p>;
  }
  return (
    <ol className="list-none p-0">
      {chapters.map((chapter) => {
        return (
          <li key={chapter.slug} className="border-hair border-b py-3 last:border-b-0">
            <span className="font-mono text-[0.75rem] text-accent">{String(chapter.order).padStart(2, "0")}</span>{" "}
            <Link href={chapter.href} className="text-ink hover:text-accent">
              {chapter.title}
            </Link>
            {withRefs ? (
              <>
                {" · "}
                <span className="book-toc__ref" data-book-toc-ref={chapter.href}>
                  {""}
                </span>
              </>
            ) : null}
            <p className="m-0 max-w-[var(--measure-prose)] text-ink-soft">{chapter.summary}</p>
            {chapter.sections.length > 0 ? (
              <ol className="mt-2 list-none p-0 pl-6 font-mono text-[0.82rem]">
                {chapter.sections.map((s) => (
                  <li key={s.slug} className="py-0.5">
                    <Link href={s.href} className="text-ink-soft hover:text-ink">
                      {String(chapter.order).padStart(2, "0")}.{s.order} {s.title}
                    </Link>
                    {withRefs ? (
                      <>
                        {" · "}
                        <span className="book-toc__ref" data-book-toc-ref={s.href}>
                          {""}
                        </span>
                      </>
                    ) : null}
                  </li>
                ))}
              </ol>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
