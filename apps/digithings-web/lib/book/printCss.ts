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

/* Diagrams: one file per theme, picked by the page's data-theme. Light is the
   default and the only one print ever shows. */
.book-figure__dark { display: none; }
:root[data-theme="dark"] .book-figure__light { display: none; }
:root[data-theme="dark"] .book-figure__dark { display: block; }
.book-figure:fullscreen { background: var(--bg); display: flex; flex-direction: column; padding: 1.5rem; }
.book-figure:fullscreen .book-figure__viewport { flex: 1; }
.book-figure__viewport[data-active] { outline: 1px solid var(--ink-soft); }

/* Reference cards: the MDX paragraph inside keeps the card's own rhythm. */
.book-reference__body p { margin: 0; max-width: none; font-size: inherit; }

/* Tables (GFM) in the house long-form grammar. */
.book-chapter table { width: 100%; border-collapse: collapse; margin: 0 0 1.5rem; font-size: 0.92rem; }
.book-chapter th, .book-chapter td { border-bottom: 1px solid var(--hair); padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; color: var(--ink-soft); }
.book-chapter th { font-family: var(--font-mono); font-size: 0.78rem; letter-spacing: 0.02em; color: var(--ink); }

/* The book uses the same mono voice as the rest of digithings.ai. */
.book-root { --font-mono: var(--font-stack-mono); }

/* Code blocks (components/book/BookCode.tsx). The bar carries the copy control
   and a "scroll" hint that is only visible while the block is actually wider
   than the column: a hint you can see on a block that does not scroll teaches
   the reader to distrust the next one. */
.book-code { background: var(--surface-2); }
.book-code pre { margin: 0; }
.book-code__bar { background: var(--bg); }
.book-code__hint { visibility: hidden; }
.book-code[data-overflow="x"] .book-code__hint { visibility: visible; }
.book-code pre:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }

/* Inline code: the chapters carry a lot of it, so it needs to sit off the
   prose without becoming a box around every token. */
.book-chapter :not(pre) > code { background: var(--surface-2); padding: 0.05em 0.3em; }

/* A wide table scrolls inside its own box rather than widening the page. */
.book-table { max-width: 100%; overflow-x: auto; }
.book-table:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* The current page in the sidebar gets a 1px tick as well as a darker ink, so
   the mark is not carried by colour alone. The list already draws the hairline
   the tick sits on. */
.book-sidebar li[data-active] { margin-left: -0.75rem; padding-left: 0.75rem; box-shadow: inset 1px 0 0 var(--accent); }


@media print {
  html, body { background: transparent; }
  .book-figure__dark { display: none !important; }
  .book-figure__light { display: block !important; }
  .book-figure__viewport { border: 0; }
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
  tr { break-inside: avoid; }

  /* Printed code has no scrollbar, so it wraps instead of being clipped, and
     the copy control stays on screen where it works. */
  .book-code { border: 0; background: transparent; }
  .book-code__bar { display: none !important; }
  .book-code pre { white-space: pre-wrap; overflow-wrap: anywhere; overflow: visible; padding-left: 0; padding-right: 0; }
  .book-table { overflow: visible; }

  /* A printed link has to say where it goes. Internal links stay bare: their
     address is the book's own, and the chapter it points at is in this volume. */
  a[href^="http"]::after { content: " (" attr(href) ")"; font-size: 0.85em; overflow-wrap: anywhere; color: var(--ink-soft); }

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
[role="status"], .skip-link, .book-code__bar { display: none !important; }

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
/* 132mm keeps the printed measure near the reading column on screen; the full
   A4 text width at 10.5pt runs past 100 characters a line. */
p { margin: 0 0 8pt; max-width: 132mm; }
ul, ol { margin: 0 0 8pt 18pt; max-width: 132mm; }
li { margin: 0 0 3pt; }
code, pre { font-family: var(--font-mono), monospace; }
/* Printed code has no scrollbar: it wraps rather than losing its tail. */
pre { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 8.5pt; margin: 0 0 10pt; }
img { max-width: 100%; }
.book-figure__dark { display: none !important; }
.book-figure__light { display: block !important; }
table { width: 100%; border-collapse: collapse; font-size: 8.5pt; margin: 0 0 10pt; }
th, td { border-bottom: 0.4pt solid var(--hair); padding: 2pt 4pt; text-align: left; vertical-align: top; }
tr { break-inside: avoid; }
pre { line-height: 1.25; }
h1, h2, h3, h4 { break-after: avoid; }
p, pre, img, li { break-inside: avoid; }
a { color: inherit; text-decoration: none; }
/* A printed link has to say where it goes; internal ones point inside this
   volume, so their address is redundant. */
a[href^="http"]::after { content: " (" attr(href) ")"; font-size: 8pt; overflow-wrap: anywhere; color: var(--ink-soft); }
`;

export default PRINT_CSS;
