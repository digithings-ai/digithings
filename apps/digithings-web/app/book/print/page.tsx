import type { Metadata } from "next";

import BookDocument from "@/components/book/BookDocument";

/**
 * The print artefact is a rendering of the same book content with PagedJS
 * chrome; it is not a destination page. Keep it out of the index (searchers
 * want /book, which is where we send them instead).
 */
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

/**
 * The printed book. The document itself lives in `BookDocument` because the
 * reader at `/book` paginates the same one; this route only decides that it is
 * a print destination.
 *
 * The wrapper is the signal the shared print sheet uses to hide the site's
 * chrome — header, footer, skip link. On this route there is nothing to
 * navigate to; on `/book` those rules must not fire, because the reader needs
 * its own contents.
 */
export default function BookPrintPage() {
  return (
    <div className="book-print">
      <BookDocument />
    </div>
  );
}

export const dynamic = "force-static";
