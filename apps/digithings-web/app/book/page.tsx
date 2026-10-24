import type { Metadata } from "next";
import Link from "next/link";

import { PageHead } from "@digithings/ui";

import BookToc from "@/components/book/BookToc";
import { chapterRefs, loadChapters } from "@/lib/book/chapters.server";

export const metadata: Metadata = {
  alternates: { canonical: "/book/" },
};

/**
 * The book's index: every chapter, in the order its author chose.
 *
 * The canonical is declared here rather than in `layout.tsx`; a layout's
 * canonical is inherited by every route under it (see `app/book/layout.tsx`).
 */
export default function BookIndexPage() {
  const chapters = chapterRefs(loadChapters(process.cwd()));
  return (
    <article className="pt-[clamp(3rem,7vw,5rem)]">
      <PageHead kicker="// digibook" title="digibook">
        A short book about self-hosted AI infrastructure: why it matters, how it scales, and what it
        costs. It is not a technical manual, because the docs already are one. This is the thinking
        behind the choice to own the stack at all.
      </PageHead>
      <div className="mt-[clamp(2rem,4vw,3rem)] max-w-[var(--measure-prose)]">
        <BookToc chapters={chapters} />
      </div>
      <p className="book-screen-only mt-10 font-mono text-[0.8rem] text-ink-soft">
        <Link href="/book/print/" className="text-accent">
          printable edition
        </Link>
      </p>
    </article>
  );
}
