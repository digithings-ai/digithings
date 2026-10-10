"use client";

/**
 * Loads Paged.js on the printable route (DIG-2821).
 *
 * Two rules this component exists to enforce:
 *
 *  1. **Print-only.** Paged.js rewrites the document into fixed-size page
 *     boxes. On screen that would destroy the reading layout, so it is loaded
 *     only under `/book/print` AND only when printing is actually asked for.
 *     A preview on screen uses the same route without pagination, so what a
 *     human checks is the same document the PDF is made from.
 *  2. **Idle, not blocking.** `requestIdleCallback` so the paginated DOM is not
 *     swapped in while the reader is scrolling to the first chapter.
 *
 * The page-number pass runs after `chunker.chunk()` and writes the ToC's page
 * references from the anchors the engine produced. That is the whole reason
 * this is a client component: the number is not knowable on the server.
 */
import { useEffect, useRef, useState } from "react";

import { PAGED_CSS } from "@/lib/book/printCss";

export default function PagedBoot({ enabled }: { enabled: boolean }) {
  const [status, setStatus] = useState<"idle" | "paginating" | "done" | "failed">("idle");
  const cleanups = useRef<(() => void)[]>([]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const run = async () => {
      setStatus("paginating");
      try {
        const { Previewer } = await import("pagedjs");
        const previewer = new Previewer();
        // `preview(content, stylesheets, renderTo)`: the SECOND argument is the
        // `preview(content, stylesheets, renderTo)`: the second argument is the
        // stylesheet list. It is the book's OWN sheet, and deliberately not
        // `undefined` (which means "strip the page's stylesheets and take the
        // page over") — pagedjs parses every selector it is handed, and the
        // site's Tailwind arbitrary values make it throw before it paginates
        // anything. See lib/book/printCss.ts.
        //
        // `content` is ONE node (or its HTML), not a list: pagedjs hands it
        // straight to `createTreeWalker`, and an array is not a Node. There is
        // one paginated element on this route, so it is that element.
        const content = document.querySelector<HTMLElement>("[data-paged-content]");
        if (!content) throw new Error("no [data-paged-content] element to paginate");
        const chunker = await previewer.preview(content, [PAGED_CSS], document.documentElement);
        if (cancelled) return;
        // The chunker allocates pages; they have to be cleaned up when the
        // route is left, or a second visit doubles the document.
        cleanups.current.push(() => chunker.destroy());
        stampPages();
        fillTocPageRefs();
        // The print step waits on THIS attribute, not on `.pagedjs_page`:
        // pagedjs creates the page boxes before the numbers exist, so waiting
        // for boxes printed the table of contents with every reference still
        // empty. Measured, not assumed.
        content.dataset.bookPaginated = String(document.querySelectorAll(".pagedjs_page").length);
        setStatus("done");
      } catch (err) {
        console.error("book: pagination failed", err);
        setStatus("failed");
      }
    };

    const when = window.requestIdleCallback
      ? (fn: () => void) => window.requestIdleCallback(fn, { timeout: 2000 })
      : (fn: () => void) => window.setTimeout(fn, 200);
    const handle = when(run);

    return () => {
      cancelled = true;
      window.cancelIdleCallback?.(handle as number);
      cleanups.current.splice(0).forEach((fn) => fn());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // Dev-visible: a pagination failure must be visible in the exported HTML, not
  // only in a console nobody reads in CI.
  if (status === "failed") {
    return (
      <p className="book-paged-status book-print-only" role="status">
        pagination failed — the printed page numbers are missing
      </p>
    );
  }
  if (status === "paginating") {
    return (
      <p className="book-paged-status" role="status">
        paginating…
      </p>
    );
  }
  return null;
}

/**
 * Number the page boxes, then write each table-of-contents entry's reference.
 *
 * Two passes, in this order, because neither can be done first:
 *
 *  1. `stampPages` numbers every `.pagedjs_page` in document order and writes it
 *     to `data-book-page`. Nothing else stamps it — a reference that reads an
 *     attribute nobody writes is a reference that stays empty on every page
 *     while the mechanism looks like it is working.
 *  2. `fillTocPageRefs` resolves each entry through its OWN href, the same link
 *     the web page uses, so the printed number and the screen link cannot name
 *     different chapters. An entry whose anchor is missing leaves its cell
 *     empty rather than inventing a number.
 *
 * The lookup is scoped to `.pagedjs_page` on purpose. pagedjs leaves the
 * original content in the document AND places a copy inside each page box, so
 * there are two elements per chapter; an unscoped `querySelector` returns the
 * first one, which is outside every page, and every reference comes back empty
 * while the mechanism looks installed. Measured: 6 anchors for 3 chapters,
 * pages 2 / 3 / 6.
 */
function stampPages(): void {
  document.querySelectorAll<HTMLElement>(".pagedjs_page").forEach((page, index) => {
    page.dataset.bookPage = String(index + 1);
  });
}

function fillTocPageRefs(): void {
  for (const ref of document.querySelectorAll<HTMLElement>("[data-book-toc-ref]")) {
    const href = ref.dataset.bookTocRef;
    if (!href) continue;
    const target = document.querySelector<HTMLElement>(
      `.pagedjs_page [data-book-anchor="${CSS.escape(href)}"]`,
    );
    const page = target?.closest<HTMLElement>(".pagedjs_page")?.dataset.bookPage;
    ref.textContent = page ?? "";
  }
}
