import Link from "next/link";

import type { SectionRef } from "@/lib/book/toc";

/**
 * Previous / next section links at the foot of every book page (DIG-2821, U17).
 * They walk the whole book in reading order, so they cross chapter boundaries.
 *
 * Two fixed columns rather than two floated halves: the old `max-w-[48%]` plus
 * a gap summed to more than 100% and pushed the page sideways on a phone. Each
 * link names the direction in words; the glyph arrows that used to carry it
 * were decoration on top of a label that already said "previous".
 */
export default function SectionNav({ previous, next }: { previous: SectionRef | null; next: SectionRef | null }) {
  const card =
    "flex min-w-0 flex-col gap-1 border border-hair px-4 py-3 font-mono text-[0.8rem] hover:border-hair-2 focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-ink";
  return (
    <nav
      aria-label="Reading order"
      className="book-screen-only mt-16 grid grid-cols-1 gap-4 border-hair border-t pt-6 sm:grid-cols-2"
    >
      {previous ? (
        <Link href={previous.href} className={card} rel="prev">
          <span className="text-[0.7rem] text-ink-soft">previous</span>
          <span className="text-ink">{previous.title}</span>
        </Link>
      ) : (
        <Link href="/book/" className={card}>
          <span className="text-[0.7rem] text-ink-soft">start of the book</span>
          <span className="text-ink">contents</span>
        </Link>
      )}
      {next ? (
        <Link href={next.href} className={`${card} sm:text-right`} rel="next">
          <span className="text-[0.7rem] text-ink-soft">next</span>
          <span className="text-ink">{next.title}</span>
        </Link>
      ) : (
        <Link href="/book/" className={`${card} sm:text-right`}>
          <span className="text-[0.7rem] text-ink-soft">end of the book</span>
          <span className="text-ink">back to contents</span>
        </Link>
      )}
    </nav>
  );
}
