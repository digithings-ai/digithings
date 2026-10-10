import Link from "next/link";

import type { ChapterRef } from "@/lib/book/toc";

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
  activeSlug,
  withRefs = false,
}: {
  chapters: readonly ChapterRef[];
  activeSlug?: string;
  /** Print route only: reserve the column the page references land in. */
  withRefs?: boolean;
}) {
  if (chapters.length === 0) {
    return <p className="font-mono text-ink-soft">no chapters yet</p>;
  }
  return (
    <ol className="list-none p-0">
      {chapters.map((chapter) => {
        const active = chapter.slug === activeSlug;
        return (
          <li key={chapter.slug} className="border-hair border-b py-3 last:border-b-0">
            <span className="font-mono text-[0.75rem] text-accent">{String(chapter.order).padStart(2, "0")}</span>{" "}
            <Link
              href={chapter.href}
              aria-current={active ? "page" : undefined}
              className={active ? "text-ink" : "text-ink-soft"}
            >
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
            <p className="m-0 text-ink-soft">{chapter.summary}</p>
          </li>
        );
      })}
    </ol>
  );
}
