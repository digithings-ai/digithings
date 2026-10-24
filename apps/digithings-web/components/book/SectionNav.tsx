import Link from "next/link";

import type { SectionRef } from "@/lib/book/toc";

/**
 * Previous / next section buttons at the foot of every book page. They walk
 * the whole book in reading order, so they cross chapter boundaries.
 */
export default function SectionNav({ previous, next }: { previous: SectionRef | null; next: SectionRef | null }) {
  const card =
    "block min-w-0 border border-hair px-4 py-3 font-mono text-[0.8rem] transition-colors hover:border-ink-soft focus-visible:outline focus-visible:outline-1 focus-visible:outline-ink";
  return (
    <nav
      aria-label="Sections"
      className="book-screen-only mt-16 grid grid-cols-1 gap-3 border-hair border-t pt-6 sm:grid-cols-2"
    >
      {previous ? (
        <Link href={previous.href} className={card} rel="prev">
          <span className="block text-ink-soft">← previous</span>
          <span className="mt-1 block leading-snug text-ink">{previous.title}</span>
        </Link>
      ) : (
        <Link href="/book/" className={card}>
          <span className="block text-ink-soft">← contents</span>
        </Link>
      )}
      {next ? (
        <Link href={next.href} className={`${card} sm:text-right`} rel="next">
          <span className="block text-ink-soft">next →</span>
          <span className="mt-1 block leading-snug text-ink">{next.title}</span>
        </Link>
      ) : null}
    </nav>
  );
}
