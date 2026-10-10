import Link from "next/link";

import { chapterNeighbours, type ChapterRef } from "@/lib/book/toc";

/**
 * The previous/next pair at the foot of a chapter (DIG-2821).
 *
 * Takes the neighbours already computed by `chapterNeighbours`, which returns
 * null at either end. A null renders the book's own index rather than a link
 * that goes nowhere.
 */
export default function ChapterNav({
  chapters,
  slug,
}: {
  chapters: readonly ChapterRef[];
  slug: string;
}) {
  const { previous, next } = chapterNeighbours(chapters, slug);
  return (
    <nav aria-label="Chapters" className="book-screen-only mt-16 border-hair border-t pt-6">
      <div className="flex justify-between">
        <span>
          {previous ? (
            <Link href={previous.href} className="font-mono text-[0.8rem] text-ink-soft">
              ← {previous.title}
            </Link>
          ) : (
            <Link href="/book/" className="font-mono text-[0.8rem] text-ink-soft">
              ← book index
            </Link>
          )}
        </span>
        {next ? (
          <Link href={next.href} className="font-mono text-[0.8rem] text-ink-soft">
            {next.title} →
          </Link>
        ) : null}
      </div>
    </nav>
  );
}
