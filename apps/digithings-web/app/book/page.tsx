import Link from "next/link";

import { PageHead } from "@digithings/ui";

import BookDownloadButton from "@/components/book/BookDownloadButton";
import BookToc from "@/components/book/BookToc";
import { chapterRefs, loadChapters } from "@/lib/book/chapters.server";

/** The book's index: every chapter, in the order its author chose. */
export default function BookIndexPage() {
  const chapters = chapterRefs(loadChapters(process.cwd()));
  return (
    <article className="pt-[clamp(3rem,7vw,5rem)]">
      <PageHead kicker="// digibook" title="digibook">
        A short, philosophical book about self-hosted AI infrastructure: why it matters, how it
        scales, and what it costs. It is not a technical manual for digithings — the docs cover
        that — this is the thinking behind choosing to own your own stack at all.
      </PageHead>
      <div className="mt-[clamp(2rem,4vw,3rem)] max-w-[64ch]">
        <BookToc chapters={chapters} />
      </div>
      <p className="book-screen-only mt-10 flex flex-wrap items-baseline gap-x-4 gap-y-2 font-mono text-[0.8rem] text-ink-soft">
        <BookDownloadButton className="inline-flex min-h-11 items-center border-hair border-b text-accent hover:text-ink" />
        <Link href="/book/print/" className="text-accent hover:text-ink">
          printable edition
        </Link>
      </p>
    </article>
  );
}
