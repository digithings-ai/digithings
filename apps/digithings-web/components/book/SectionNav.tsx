import Link from "next/link";

import type { SectionRef } from "@/lib/book/toc";

/**
 * Previous / next section buttons at the foot of every book page. They walk
 * the whole book in reading order, so they cross chapter boundaries.
 */
export default function SectionNav({ previous, next }: { previous: SectionRef | null; next: SectionRef | null }) {
  const card = "block max-w-[48%] border border-hair px-4 py-3 font-mono text-[0.8rem]";
  return (
    <nav aria-label="Sections" className="book-screen-only mt-16 flex justify-between gap-4 border-hair border-t pt-6">
      {previous ? (
        <Link href={previous.href} className={card} rel="prev">
          <span className="block text-ink-soft">← previous</span>
          <span className="text-ink">{previous.title}</span>
        </Link>
      ) : (
        <Link href="/book/" className={card}>
          <span className="block text-ink-soft">← contents</span>
        </Link>
      )}
      {next ? (
        <Link href={next.href} className={`${card} ml-auto text-right`} rel="next">
          <span className="block text-ink-soft">next →</span>
          <span className="text-ink">{next.title}</span>
        </Link>
      ) : null}
    </nav>
  );
}
