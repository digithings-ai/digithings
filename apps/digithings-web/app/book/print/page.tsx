import type { Metadata } from "next";

import BookDocument from "@/components/book/BookDocument";
import { PRINT_CSS } from "@/lib/book/printCss";

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
 */
/**
 * The print sheet is injected here, not in the layout, because it hides the
 * site's chrome unconditionally (header, footer, every nav) and would take the
 * reader's own contents with it on `/book`.
 */
export default function BookPrintPage() {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: PRINT_CSS }} />
      <BookDocument />
    </>
  );
}

export const dynamic = "force-static";
