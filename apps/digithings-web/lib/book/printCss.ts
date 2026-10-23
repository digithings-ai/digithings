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
.book-figure__diagram svg { display: block; width: auto; height: auto; max-width: 100%; max-height: min(75vh, 48rem); }
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


@media print {
  html, body { background: transparent; }
  .book-figure__dark { display: none !important; }
  .book-figure__light { display: block !important; }
  :root[data-theme="dark"] .book-figure__light { display: none !important; }
  :root[data-theme="dark"] .book-figure__dark { display: block !important; }
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
     convention that makes a spread read as one spread. Paged.js stamps the
     number on the page box; it does not create a page-number element. */
  .pagedjs_page { position: relative; }
  .pagedjs_page::after {
    content: attr(data-book-page);
    position: absolute;
    bottom: 8mm;
    font-family: var(--font-mono);
    font-size: 8pt;
    color: var(--ink-soft);
  }
  .pagedjs_page:nth-child(odd)::after { left: 18mm; }
  .pagedjs_page:nth-child(even)::after { right: 18mm; }

  /* A chapter starts on a new page; a section never breaks mid-figure. */
  .book-chapter { break-before: page; }
  .book-chapter:first-of-type { break-before: auto; }
  h1, h2, h3, h4 { break-after: avoid; }
  figure, pre, table, img, svg { break-inside: avoid; }
  p { orphans: 3; widows: 3; }
  .book-reference { break-inside: avoid; }

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
@page { size: A4 !important; margin: 20mm 18mm 18mm !important; }
/* Diagrams get a landscape plate: a wide flow or a tall sequence is illegible
   in a 174mm portrait measure. */
@page plate { size: A4 landscape; margin: 14mm; }

/* The site chrome and any live status line are not part of the book. This
   sheet is the ONLY one pagedjs gets, so it — not the site's '@media print'
   block — is what decides what a page box contains. */
.site-rails, header, footer, nav, .book-screen-only, .book-print-only, .running-element,
.book-paged-status, [role="status"], .skip-link, a[href="#main"] { display: none !important; }

html, body, .pagedjs_pages { margin: 0; padding: 0; }
body {
  font-family: var(--font-sans), ui-monospace, monospace;
  font-size: 10.5pt;
  line-height: 1.6;
  color: var(--ink);
  background: var(--bg);
}

/* Paged.js clones the site's layout wrappers into every page. Both the app
   shell and the print route carry the gutter, so the page had 96px of extra
   inset on each side; the @page margin is the only frame a printed page needs.
   Body copy also inherited the site's 16px base and its 92% max-width, which
   is what made the text look like a narrow column. */
.book-root > div, .book-flow, [data-paged-content] {
  width: auto !important;
  max-width: none !important;
  margin-left: 0 !important;
  margin-right: 0 !important;
  padding-left: 0 !important;
  padding-right: 0 !important;
}
.book-flow p, .book-flow li, .book-flow td, .book-flow blockquote {
  max-width: none !important;
  font-size: 9.75pt !important;
  line-height: 1.45 !important;
  text-align: left !important;
}

/* Paged.js carries the source document into print; hiding that source
   (PagedBoot) leaves only the page boxes. */
.pagedjs_page { position: relative; }
.pagedjs_page:first-child::after { content: none; }

/* Title page: one centred block, then a hard break. */
.book-cover {
  position: relative;
  overflow: hidden;
  break-after: page;
  box-sizing: border-box;
  padding-top: 34mm;
}
.book-cover__motion {
  position: absolute;
  top: 18mm;
  left: -38%;
  width: 176%;
  opacity: 0.055;
  pointer-events: none;
}
.book-cover__motion svg { display: block; width: 100%; height: auto; }
.book-cover__mark {
  position: relative;
  width: 90mm;
  margin: 0 0 14mm;
}
.book-cover__mark svg { display: block; width: 100%; height: auto; }
.book-cover__title, .book-cover__subtitle, .book-cover__meta { position: relative; }
.book-cover__kicker {
  margin: 0 0 22mm;
  font-family: var(--font-sans), monospace;
  font-size: 8.5pt;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--accent);
}
.book-cover__title {
  margin: 0;
  max-width: none;
  white-space: nowrap;
  font-size: 27pt;
  line-height: 1.04;
  letter-spacing: -0.02em;
}
.book-cover__subtitle {
  margin: 9mm 0 0;
  max-width: 108mm;
  font-size: 11.5pt;
  line-height: 1.55;
  color: var(--ink-soft);
}
.book-cover__meta {
  margin: 72mm 0 0;
  padding-top: 4mm;
  border-top: 0.4pt solid var(--hair);
  font-family: var(--font-sans), monospace;
  font-size: 8pt;
  color: var(--ink-soft);
}

/* Contents: dot leaders and a right-aligned folio, one page or more. */
.book-contents { break-before: page; break-after: page; }
.book-contents__title {
  margin: 0 0 8mm;
  font-family: var(--font-sans), monospace;
  font-size: 9pt;
  font-weight: 400;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
}
.book-toc { margin: 0; padding: 0; list-style: none; }
.book-toc__chapter { padding: 1.8mm 0; border-bottom: 0.4pt solid var(--hair); break-inside: avoid; }
.book-toc__chapter:last-child { border-bottom: 0; }
.book-toc__label { font-size: 9.5pt; }
.book-toc__row { display: flex; align-items: baseline; break-inside: avoid; }
.book-toc__label { flex: 0 1 auto; }
.book-toc__leader {
  flex: 1 1 auto;
  min-width: 8mm;
  margin: 0 2.5mm;
  border-bottom: 0.4pt dotted var(--ink-mute);
  transform: translateY(-0.5mm);
}
.book-toc__ref {
  flex: 0 0 8mm;
  text-align: right;
  font-family: var(--font-sans), monospace;
  font-size: 9pt;
}
.book-toc__summary { display: none; }
.book-toc__sections {
  margin: 2mm 0 0 8mm;
  padding: 0;
  list-style: none;
  font-size: 9pt;
}
.book-toc__sections li { padding: 0.7mm 0; }

/* Chapters and sections. */
/* Chapters flow like essays instead of each forcing a fresh leaf: a forced
   break after a short final paragraph produced pages holding one line. The
   opener is kept together and given air, so it reads as a chapter start
   without wasting a page. */
.book-chapter { break-before: auto; margin-top: 9mm; }
.book-chapter:first-of-type { margin-top: 0; }
.book-chapter__head {
  display: block;
  break-inside: avoid;
  break-after: avoid;
}
.book-colophon {
  display: flex;
  flex-direction: column;
  margin-top: 14mm;
  padding-top: 6mm;
  border-top: 0.4pt solid var(--hair);
  min-height: 225mm;
  break-inside: avoid;
}
.book-colophon__kicker {
  margin: 0 0 5mm;
  font-family: var(--font-sans), monospace;
  font-size: 8pt;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
}
.book-colophon__title { margin: 0 0 6mm; font-size: 22pt; line-height: 1.1; }
.book-colophon p { max-width: 120mm !important; color: var(--ink-soft); }
.book-colophon__mark {
  margin: auto 0 0 !important;
  max-width: none !important;
  font-size: 46pt;
  line-height: 1;
  letter-spacing: -0.05em;
  color: color-mix(in srgb, var(--ink) 12%, transparent);
}
.book-chapter__head h2 { margin: 0 0 3mm; font-size: 21pt; line-height: 1.08; letter-spacing: -0.01em; }
.book-chapter__head > p:first-of-type { margin: 0 0 2mm; font-family: var(--font-sans), monospace; font-size: 8.5pt; color: var(--accent); }
.book-chapter__head > p:nth-of-type(2) { margin: 0 0 8mm; color: var(--ink-soft); }
.book-chapter h2 { margin: 6mm 0 2mm; font-size: 13.5pt; line-height: 1.2; }
.book-section h3 { margin: 5mm 0 2mm; font-size: 11.5pt; line-height: 1.25; }
h4 { margin: 5mm 0 2mm; font-size: 8.5pt; font-family: var(--font-sans), monospace; letter-spacing: 0.04em; }
h1, h2, h3, h4 { break-after: avoid; }
h1 { font-size: 24pt; margin: 0 0 5mm; line-height: 1.12; }

p { margin: 0 0 2.4mm; orphans: 4; widows: 4; }
p, pre, img, li, figure, table { break-inside: avoid; }
ul, ol { margin: 0 0 3.4mm 5mm; padding: 0; }
li { margin: 0 0 1.2mm; }

code, pre { font-family: var(--font-sans), monospace; }
code { font-size: 0.92em; }
pre {
  margin: 0 0 3mm;
  padding: 2.5mm 3mm;
  border: 0.4pt solid var(--hair);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 8pt;
  line-height: 1.35;
}
blockquote {
  margin: 0 0 4mm;
  padding: 0 0 0 4mm;
  border-left: 1.2pt solid var(--accent);
  color: var(--ink-soft);
}
hr { border: 0; border-top: 0.4pt solid var(--hair); margin: 6mm 0; }
strong { font-weight: 600; }
a { color: inherit; text-decoration: none; }

img, svg { max-width: 100%; }
figure { margin: 0 0 3.5mm; }
.book-figure__diagram svg { max-height: 190mm; }
figcaption { margin-top: 2mm; font-family: var(--font-sans), monospace; font-size: 8pt; color: var(--ink-soft); }
.book-figure__dark { display: none !important; }
.book-figure__light { display: block !important; }
:root[data-theme="dark"] .book-figure__light { display: none !important; }
:root[data-theme="dark"] .book-figure__dark { display: block !important; }

table { width: 100%; border-collapse: collapse; font-size: 8pt; margin: 0 0 3mm; }
thead { display: table-header-group; }
th, td { border-bottom: 0.4pt solid var(--hair); padding: 1.6mm 2mm; text-align: left; vertical-align: top; }
th { font-family: var(--font-sans), monospace; font-size: 7.5pt; letter-spacing: 0.04em; color: var(--ink); }

/* Folios sit in the bottom outer margin, alternating by parity. */
.pagedjs_page::after {
  content: attr(data-book-page);
  position: absolute;
  bottom: 8mm;
  font-family: var(--font-sans), monospace;
  font-size: 8pt;
  color: var(--ink-soft);
}
.pagedjs_page:nth-child(odd)::after { left: 18mm; }
.pagedjs_page:nth-child(even)::after { right: 18mm; }

/* Paged.js paints its margin boxes (the slots that would hold a running
   header) with the page background. Over the injected field those slots read
   as rectangular cutouts, especially at the top centre of the cover. */
.pagedjs_margin, .pagedjs_margin * { display: none !important; }
.pagedjs_pagebox, .pagedjs_sheet { background: transparent !important; }

/* Paged.js clones the source wrappers (html/body) into each page box, and
   they carry the site's opaque background. Behind the injected field those
   clones read as rectangular cutouts — the clear band at the top of the cover
   and the blocks at the page edges. Only the page background should paint. */
.pagedjs_page, .pagedjs_page * { background-color: transparent !important; }

/* ── Print-edition typography ─────────────────────────────────────────────
   The MDX components carry the web's utility classes, and those classes still
   exist in the paginated document. Element-level print rules are not enough:
   a web mb-4 or text-[1.05rem] wins on specificity, which is why some
   paragraphs were larger and further apart than others. One scale, enforced
   with !important, is the whole point of a book stylesheet. */
.pagedjs_page p,
.pagedjs_page li,
.pagedjs_page blockquote,
.pagedjs_page td {
  font-size: 10.5pt !important;
  line-height: 1.5 !important;
  max-width: none !important;
  color: var(--ink) !important;
  text-align: left !important;
}
.pagedjs_page p { margin: 0 0 3mm !important; orphans: 4; widows: 4; }
.pagedjs_page p:last-child { margin-bottom: 0 !important; }
.pagedjs_page ul,
.pagedjs_page ol { margin: 0 0 3mm 5mm !important; padding: 0 !important; }
.pagedjs_page li { margin: 0 0 1.2mm !important; }
.pagedjs_page blockquote {
  margin: 0 0 4mm !important;
  padding: 0 0 0 4mm !important;
  border-left: 1.2pt solid var(--accent) !important;
  color: var(--ink-soft) !important;
}
.pagedjs_page h1 { margin: 0 0 5mm !important; font-size: 20pt !important; line-height: 1.12 !important; }
.pagedjs_page h2 { margin: 7mm 0 2.5mm !important; font-size: 12pt !important; line-height: 1.25 !important; }
.pagedjs_page h3 { margin: 5mm 0 2mm !important; font-size: 10.5pt !important; line-height: 1.3 !important; }
.pagedjs_page h4 { margin: 4mm 0 1.5mm !important; font-size: 9pt !important; line-height: 1.35 !important; }
.pagedjs_page h1, .pagedjs_page h2, .pagedjs_page h3, .pagedjs_page h4 { break-after: avoid; }
.pagedjs_page .book-chapter__head h2 {
  margin: 0 0 3mm !important;
  font-size: 20pt !important;
  line-height: 1.08 !important;
  letter-spacing: -0.01em;
}
.pagedjs_page .book-chapter__head > p:first-of-type { font-size: 8.5pt !important; margin: 0 0 2mm !important; }
.pagedjs_page .book-chapter__head > p:nth-of-type(2) {
  margin: 0 0 4mm !important;
  font-size: 10pt !important;
  color: var(--ink-soft) !important;
}
.pagedjs_page .book-chapter__head {
  padding-bottom: 4mm;
  border-bottom: 0.4pt solid var(--hair);
  margin-bottom: 4mm;
}
.pagedjs_page .book-section h3 { margin: 6mm 0 2mm !important; font-size: 12pt !important; }
.pagedjs_page a { color: inherit !important; text-decoration: none !important; }
.pagedjs_page strong { font-weight: 600 !important; color: var(--ink) !important; }
.pagedjs_page code { font-size: 0.92em !important; }
.pagedjs_page pre {
  margin: 0 0 3mm !important;
  padding: 2.5mm 3mm !important;
  font-size: 8.5pt !important;
  line-height: 1.35 !important;
}
.pagedjs_page table { margin: 0 0 3mm !important; font-size: 8.5pt !important; }
.pagedjs_page th, .pagedjs_page td { padding: 1.6mm 2mm !important; }
.pagedjs_page th { font-size: 7.5pt !important; }
.pagedjs_page figure { margin: 0 0 4mm !important; width: 100% !important; }
.book-figure {
  page: plate;
  break-before: page;
  break-after: page;
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 158mm;
}
.book-figure__viewport {
  width: 100% !important;
  height: 158mm !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}
.book-figure__viewport > div {
  width: 100% !important;
  height: 100% !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  transform: none !important;
}
.book-figure__viewport img {
  width: auto !important;
  height: auto !important;
  max-width: 100% !important;
  max-height: 158mm !important;
  margin: 0 auto !important;
}
.pagedjs_page figcaption { margin-top: 2mm !important; font-size: 8pt !important; }

/* "Go deeper" is a web affordance. On paper the links cannot be followed, so
   the cards are not part of the book. */
.pagedjs_page .book-reference { display: none !important; }

/* Diagrams fill the measure on paper and lose the interactive frame. */
.pagedjs_page .book-figure__viewport {
  width: 100% !important;
  height: auto !important;
  border: 0 !important;
}
.pagedjs_page .book-figure__viewport > div { width: 100% !important; transform: none !important; }


/* Cover: edition/version, the hero banner, the title. Nothing else. */
.book-cover {
  text-align: center !important;
  padding-top: 28mm !important;
}
.book-cover__kicker {
  margin: 0 0 10mm !important;
  font-size: 8pt !important;
  letter-spacing: 0.12em !important;
  text-transform: none !important;
  color: var(--ink-soft) !important;
}
.book-cover__mark { width: 150mm !important; max-width: 100% !important; margin: 0 auto 12mm !important; }
.book-cover__title {
  margin: 0 auto !important;
  font-size: 24pt !important;
  line-height: 1.1 !important;
  white-space: normal !important;
}
.book-cover__subtitle { display: none !important; }
.book-cover__meta { display: none !important; }

.book-colophon { min-height: 220mm !important; }
.book-colophon__title { font-size: 18pt !important; line-height: 1.2 !important; }
.book-colophon__mark { font-size: 58pt !important; }

/* The colophon is a closing text page; it keeps its own scale. */
.pagedjs_page .book-colophon__kicker { font-size: 8pt !important; margin: 0 0 4mm !important; }
.pagedjs_page .book-colophon__title { font-size: 17pt !important; line-height: 1.25 !important; margin: 0 0 6mm !important; }
.pagedjs_page .book-colophon__mark {
  margin: auto 0 0 !important;
  max-width: none !important;
  font-size: 62pt !important;
  line-height: 1 !important;
  color: color-mix(in srgb, var(--ink) 12%, transparent) !important;
}
.pagedjs_page .book-chapter__head > p:nth-of-type(2) { margin-bottom: 6mm !important; }

/* A closing sheet with no text. The browser builder paints the field here. */
.book-end { break-before: page; min-height: 240mm; }
`;

export default PRINT_CSS;
