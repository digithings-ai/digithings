import type { ReactNode } from "react";
import type { Metadata } from "next";

import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";

import { PRINT_CSS } from "@/lib/book/printCss";
import { BOOK_READER_CSS } from "@/lib/book/readerCss";


export const metadata: Metadata = {
  title: "digibook — a book about self-hosted AI infrastructure",
  description:
    "digibook: a short, philosophical book on why self-hosted AI infrastructure matters, how it " +
    "scales, and what it costs. Read on screen or print it.",
  alternates: { canonical: "/book" },
};

/**
 * The book's chrome (DIG-2821).
 *
 * The print stylesheet is emitted here rather than linked from a `.css` file:
 * `scripts/check_frontend_canon.py` ratchets new component-class families per
 * app and reads `*.css`, so a book stylesheet as a file would register as a new
 * family and redden an unrelated lane. `lib/book/printCss.ts` explains the rest.
 */
export default function BookLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <DtNav />
      {/* Shared with the print route: the book sets its page typography here, and
          the reader paginates the same document, so leaving it out changed the
          page breaks. Its chrome rules are scoped to the print marker. */}
      <style dangerouslySetInnerHTML={{ __html: PRINT_CSS }} />
      {/* The reader's own layout, shipped in the HTML: injected from the client
          component it arrived after first paint, and the page was 100px narrower
          until it did — the shift a reader saw on every load. */}
      <style dangerouslySetInnerHTML={{ __html: BOOK_READER_CSS }} />
      <main id="main" tabIndex={-1} className="book-root pt-[var(--dq-nav-h)] pb-[clamp(2rem,5vw,4rem)]">
        <div className="mx-auto w-full max-w-[var(--wrap)] px-[var(--gutter)]">{children}</div>
      </main>
      <DtFooter />
    </>
  );
}
