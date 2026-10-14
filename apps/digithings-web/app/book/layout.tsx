import type { ReactNode } from "react";
import type { Metadata } from "next";

import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";

import { PRINT_CSS } from "@/lib/book/printCss";

export const metadata: Metadata = {
  title: "book — digithings, in reading order",
  description:
    "The digithings book: why the stack is built the way it is, in the order that makes the answer " +
    "readable. Read on screen or print it.",
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
      <style dangerouslySetInnerHTML={{ __html: PRINT_CSS }} />
      <main id="main" tabIndex={-1} className="book-root pt-[var(--dq-nav-h)] pb-[clamp(2rem,5vw,4rem)]">
        <div className="mx-auto w-full max-w-[var(--wrap)] px-[var(--gutter)]">{children}</div>
      </main>
      <DtFooter />
    </>
  );
}
