import { PageHead } from "@digithings/ui";

import BookToc from "@/components/book/BookToc";
import { chapterRefs, loadChapters } from "@/lib/book/chapters.server";

/** The book's index: every chapter, in the order its author chose. */
export default function BookIndexPage() {
  const chapters = chapterRefs(loadChapters(process.cwd()));
  return (
    <article className="pt-[clamp(3rem,7vw,5rem)]">
      <PageHead kicker="// book" title="The digithings book">
        Nine modules and the reasoning behind them, in the order that makes the answer readable. Every
        chapter is one file; the diagrams are the same files the printed book uses.
      </PageHead>
      <div className="mt-[clamp(2rem,4vw,3rem)] max-w-[64ch]">
        <BookToc chapters={chapters} />
      </div>
      <p className="book-screen-only mt-10 font-mono text-[0.8rem] text-ink-soft">
        <a href="/book/print/" className="text-accent">
          printable edition
        </a>
      </p>
    </article>
  );
}
