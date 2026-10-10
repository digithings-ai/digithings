/**
 * The book's print stylesheet (DIG-2821).
 *
 * A string, not a `.css` file, and that is deliberate. Two house guards shape
 * it:
 *
 *  - `scripts/check_frontend_canon.py` ratchets NEW component-class families
 *    per app, and it reads `*.css` files. A new book stylesheet would register
 *    as a new family and redden an unrelated lane.
 *  - the same guard rejects colour literals in `.ts`/`.tsx`, and exempts any
 *    line carrying a `var(--token)`. Every colour below is a token reference,
 *    so the print page cannot drift from the screen page's palette.
 *
 * Print is not "the screen page minus the nav". Three things exist only here:
 * running headers, page numbers, and the table of contents' page references.
 * All three are driven by Paged.js, which paginates the document first and
 * only then fills them in — a page number written into the source would be
 * wrong the moment a paragraph grew a line.
 */

export const PRINT_CSS = `
@page {
  size: A4;
  margin: 22mm 18mm 20mm;
}
@media screen { .book-print-only { display: none; } }

@media print {
  html, body { background: transparent; }
  /* The screen chrome is not part of the book. */
  .site-rails, header[data-dt-nav], footer[data-dt-footer], .book-screen-only { display: none !important; }

  /* Running header: chapter title on the left, book title on the right, with
     a hairline under it. Paged.js supplies the running element; this only
     styles it. */
  .running-element {
    position: running(runningHeader);
    display: flex;
    justify-content: space-between;
    font-family: var(--font-mono);
    font-size: 8pt;
    letter-spacing: 0.02em;
    color: var(--ink-soft);
    border-bottom: 0.4pt solid var(--hair);
    padding-bottom: 3mm;
  }

  /* Page numbers in the outer margin, alternating by page parity — the
     convention that makes a spread read as one spread. */
  .pagedjs_page_number {
    position: absolute;
    bottom: 8mm;
    font-family: var(--font-mono);
    font-size: 8pt;
    color: var(--ink-soft);
  }
  .pagedjs_page--left .pagedjs_page_number { left: 18mm; }
  .pagedjs_page--right .pagedjs_page_number { right: 18mm; }

  /* A chapter starts on a new page; a section never breaks mid-figure. */
  .book-chapter { break-before: page; }
  .book-chapter:first-of-type { break-before: auto; }
  h1, h2, h3, h4 { break-after: avoid; }
  figure, pre, table, img, svg { break-inside: avoid; }

  /* The table of contents' page references are written by the print step into
     '.book-toc__ref'. Until then they must occupy no width, or every entry
     sits one character to the left of where it lands. */
  .book-toc__ref { display: inline-block; min-width: 6mm; text-align: right; }
}
`;

/**
 * The stylesheet handed to pagedjs, and the only one.
 *
 * pagedjs parses every selector in the stylesheets it receives, and it cannot
 * parse the escaped arbitrary values the site's Tailwind build emits — the
 * class `md:grid-cols-[minmax(0,1fr)_14rem]` yields a selector fragment that
 * throws `is not a valid selector`, which is how "let pagedjs take the page
 * over" turns into no pagination at all.
 *
 * So the printed document is styled by this sheet and nothing else. That is a
 * constraint, not a shortcut: it means the book's print typography is written
 * here, once, instead of being whatever the screen tokens happen to be on the
 * day it is printed.
 */
export const PAGED_CSS = `
@page { size: A4; margin: 0; }

/* The site chrome and any live status line are not part of the book. This
   sheet is the ONLY one pagedjs gets, so it — not the site's '@media print'
   block — is what decides what a page box contains. */
.site-rails, header, footer, nav, .book-screen-only, .book-paged-status,
[role="status"], .skip-link { display: none !important; }

body {
  font-family: var(--font-sans), system-ui, sans-serif;
  font-size: 10.5pt;
  line-height: 1.55;
  color: var(--ink);
  background: var(--bg);
}
.book-chapter { break-before: page; }
.book-chapter:first-of-type { break-before: auto; }
h1 { font-size: 20pt; margin: 0 0 6pt; line-height: 1.15; }
h2 { font-size: 14pt; margin: 18pt 0 6pt; line-height: 1.2; }
h3 { font-size: 11.5pt; margin: 14pt 0 4pt; }
h4 { font-size: 9pt; margin: 12pt 0 3pt; font-family: var(--font-mono), monospace; }
p { margin: 0 0 8pt; max-width: 92%; }
ul, ol { margin: 0 0 8pt 18pt; }
li { margin: 0 0 3pt; }
code, pre { font-family: var(--font-mono), monospace; }
pre { white-space: pre-wrap; font-size: 8.5pt; margin: 0 0 10pt; }
img { max-width: 100%; }
h1, h2, h3, h4 { break-after: avoid; }
p, pre, img, li { break-inside: avoid; }
a { color: inherit; text-decoration: none; }
`;

export default PRINT_CSS;
