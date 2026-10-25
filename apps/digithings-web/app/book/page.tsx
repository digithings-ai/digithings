import type { Metadata } from "next";

import BookDocument from "@/components/book/BookDocument";
import BookLive from "@/components/book/BookLive";
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
 * The pages are the paginated document itself, not pictures of it. That is what
 * lets the book follow the reader's theme and palette: the site's tokens are on
 * <html> and pagedjs copies them into every page box, so switching theme
 * repaints the book along with the rest of the site instead of serving a second
 * set of images. Pagination is stable at any window width because the page
 * boxes are A4 from `@page`, which is why the numbers beside the contents can
 * be the printed numbers — both come from the same pass the PDF is printed
 * from (`lib/book/generated/pages.json`).
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
    <BookLive
      chapters={refs.map((chapter) => ({
        slug: chapter.slug,
        title: chapter.title,
        order: chapter.order,
        page: chapter.page,
      }))}
      pageCount={pages.pages}
    >
      <BookDocument />
    </BookLive>
  );
}
