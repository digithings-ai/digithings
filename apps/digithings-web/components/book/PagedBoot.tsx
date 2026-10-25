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

import { createEmbeddingSubject } from "@/components/landing/embedding-map";
import { mountField } from "@/components/landing/pixel-field-core";
import { PAGED_CSS } from "@/lib/book/printCss";

/**
 * The field's seed. The print run passes one in the query string so both
 * editions of a build share a pattern and differ only in colour; opening the
 * route by hand gets a fresh one, which is what makes a rebuild feel new.
 */
function coverSeed(): number {
  // Server render has no location; the field is only mounted in an effect, so a
  // placeholder here is never drawn.
  if (typeof window === "undefined") return 2410;
  const raw = new URLSearchParams(window.location.search).get("seed");
  const value = raw === null ? NaN : Number(raw);
  return Number.isFinite(value) ? value : Math.floor(Math.random() * 100_000);
}

const COVER_SEED = coverSeed();

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
        // `preview(content, stylesheets, renderTo)`: the second argument is the
        // stylesheet list. It is the book's OWN sheet, and deliberately not
        // `undefined` (which means "strip the page's stylesheets and take the
        // page over") — pagedjs parses every selector it is handed, and the
        // site's Tailwind arbitrary values make it throw before it paginates
        // anything. See lib/book/printCss.ts.
        //
        // A plain string is treated as a URL by pagedjs: passing PAGED_CSS
        // directly made it fetch the stylesheet text as a path and 404. The
        // object form is the documented way to hand it CSS text; the key is
        // only a label.
        //
        // `content` is ONE node (or its HTML), not a list: pagedjs hands it
        // straight to `createTreeWalker`, and an array is not a Node. There is
        // one paginated element on this route, so it is that element.
        const content = document.querySelector<HTMLElement>("[data-paged-content]");
        if (!content) throw new Error("no [data-paged-content] element to paginate");

        // The accent is not written here, and must not be: the page boxes are
        // appended to <html>, so they inherit --accent from the document, and
        // every palette sets its own live. Freezing the computed value inline
        // was what made the book keep one palette's colour after the reader
        // switched to another.
        // Paginate only once the fonts are the ones the book is set in. pagedjs
        // measures line lengths as it flows, and the fallback face is narrower:
        // paginating before the swap fitted the use-cases chapter onto one page
        // where the printed book gives it two, so the screen had one page fewer
        // than the PDF and every number after chapter six was wrong.
        await document.fonts.ready;
        const chunker = await previewer.preview(
          content,
          [{ "book-print.css": PAGED_CSS }],
          document.documentElement,
        );
        if (cancelled) return;
        // The chunker allocates pages; they have to be cleaned up when the
        // route is left, or a second visit doubles the document.
        cleanups.current.push(() => chunker.destroy());
        stampPages();
        fillTocPageRefs();
        mountPageFields();
        // The field reveals column by column over about a second; a screenshot
        // taken at the ready marker caught only the first few columns and
        // printed a stripe down the left edge. Wait for the sweep to finish.
        await new Promise<void>((resolve) => {
          requestAnimationFrame(() => requestAnimationFrame(() => window.setTimeout(resolve, 2200)));
        });
        // The print step waits on THIS attribute, not on `.pagedjs_page`:
        // pagedjs creates the page boxes before the numbers exist, so waiting
        // for boxes printed the table of contents with every reference still
        // empty. Measured, not assumed.
        content.dataset.bookPaginated = String(document.querySelectorAll(".pagedjs_page").length);
        // Paged.js leaves the source document in place beside the page boxes.
        // In print that would emit the source as extra pages before the book —
        // measured as two blank pages, one carrying the running header. The
        // paginated copy is the only thing that should reach paper.
        content.hidden = true;
        cleanups.current.push(() => {
          content.hidden = false;
        });
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

    // Copied out of the ref: the cleanup must tear down the chunkers THIS run
    // created, not whatever the ref holds when it eventually runs.
    const created = cleanups.current;
    return () => {
      cancelled = true;
      window.cancelIdleCallback?.(handle as number);
      created.splice(0).forEach((fn) => fn());
    };
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
    // The folio is drawn by the pagination engine on the outer edge; this
    // imprints the edition and version on the other side, so a reader holding
    // one page can tell which printing it came from. The title page states it
    // already, so it is left alone.
    if (index > 0 && !page.querySelector(".book-page-imprint")) {
      const imprint = document.createElement("span");
      imprint.className = "book-page-imprint";
      imprint.textContent = "E26 · V1";
      page.appendChild(imprint);
    }
  });
}

/**
 * The cover and the contents carry the field the welcome page draws: an
 * embedding map in pixels. It is mounted here, on the page box, and not in the
 * source document: pagedjs copies the source into the boxes, and a canvas
 * copied that way arrives without its bitmap, so a field mounted before
 * pagination printed a blank page.
 *
 * It goes on the page box rather than inside the section so it can run edge to
 * edge — the section sits inside the page margins. The contents page gets the
 * same field at a lower strength and from a different seed, so the two facing
 * pages do not read as the same wallpaper.
 */
function mountPageFields(): void {
  document.querySelectorAll<HTMLElement>(".pagedjs_page").forEach((page) => {
    const cover = page.querySelector(".book-cover");
    const contents = page.querySelector(".book-contents");
    if ((!cover && !contents) || page.querySelector(".book-cover__field")) return;
    const canvas = document.createElement("canvas");
    canvas.className = cover ? "book-cover__field" : "book-cover__field book-cover__field--quiet";
    canvas.setAttribute("aria-hidden", "true");
    page.prepend(canvas);
    mountField(canvas, createEmbeddingSubject(cover ? COVER_SEED : COVER_SEED + 7));
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
