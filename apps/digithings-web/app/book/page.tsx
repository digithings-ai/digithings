import type { Metadata } from "next";

import BookPages from "@/components/book/BookPages";
import pages from "@/lib/book/generated/pages.json";
import { briefChapters } from "@/lib/book/brief";
import { chapterRefs, loadChapters } from "@/lib/book/chapters.server";

export const metadata: Metadata = {
  title: "the digithings book",
  description:
    "An open-core AI stack, explained module by module: why it runs where you put it, how the parts fit, and how to start on one machine.",
};

/**
 * The book, read the way it is printed (DIG-2821 follow-up).
 *
 * The pages below are the PDF's own pages. The contents beside them is built
 * from `lib/book/generated/pages.json`, which is read off the same pagination
 * the PDF is printed from, so a page number here is the page number in the
 * download — including when a chapter grows and both move together.
 *
 * The deeper web chapters remain at `/book/<chapter>/`; this page is the book,
 * not the documentation, and it carries the download rather than a chapter
 * index.
 */
export default async function BookIndexPage() {
  const chapters = briefChapters(loadChapters(process.cwd()));
  const refs = briefChapters(chapterRefs(chapters)).map((chapter, index) => ({
    ...chapter,
    order: index + 1,
    page: pages.map[chapter.href as keyof typeof pages.map] ?? 0,
  }));

  return (
    <BookPages
      chapters={refs.map((chapter) => ({
        slug: chapter.slug,
        title: chapter.title,
        order: chapter.order,
        page: chapter.page,
      }))}
    >
      {Array.from({ length: pages.pages }, (_, index) => {
        const number = index + 1;
        return (
          <figure
            key={number}
            id={`book-page-${number}`}
            data-book-page={number}
            className="book-frames__sheet"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              className="book-frames__page"
              src={`/book/pages/${String(number).padStart(2, "0")}.webp`}
              data-light-src={`/book/pages/${String(number).padStart(2, "0")}.webp`}
              data-dark-src={`/book/pages/dark/${String(number).padStart(2, "0")}.webp`}
              alt={`Page ${number} of the digithings book`}
              width={1240}
              height={1754}
              loading={number <= 2 ? "eager" : "lazy"}
              decoding="async"
            />
          </figure>
        );
      })}
    </BookPages>
  );
}
