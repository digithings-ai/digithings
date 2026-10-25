/**
 * Screen styles for `/book`, the paginated book (DIG-2821 follow-up).
 *
 * The page shows the pages of the printed PDF, at reading width, with the
 * contents beside them. The images are the artefact: a live re-pagination in
 * the browser reflowed with the window (19 pages at 1280px, 20 at 1440), so
 * the sidebar's page numbers stopped matching the paper. Rendering the PDF's
 * own pages is the only version that cannot disagree with the download.
 */
export const BOOK_READER_CSS = `
.book-shell {
  display: grid;
  grid-template-columns: 17rem minmax(0, 1fr);
  gap: 2.5rem;
  max-width: var(--wrap);
  margin-inline: auto;
  padding-inline: var(--gutter);
  padding-block: 1.5rem 4rem;
  align-items: start;
}
.book-nav {
  position: sticky;
  top: calc(var(--dq-nav-h) + 1.5rem);
  align-self: start;
  max-height: calc(100dvh - var(--dq-nav-h) - 3rem);
  overflow-y: auto;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.78rem;
  line-height: 1.5;
}
.book-nav__title {
  margin: 0 0 0.5rem;
  font-size: 0.72rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--color-accent, #b55e2a);
}
.book-nav ol { margin: 0; padding: 0; list-style: none; }
.book-nav li { border-bottom: 1px solid var(--color-hair, #e5e0d8); }
.book-nav a {
  display: flex;
  gap: 0.6rem;
  padding: 0.4rem;
  color: var(--color-ink-soft, #6b6560);
  text-decoration: none;
}
.book-nav a:hover,
.book-nav a[aria-current="true"] { color: var(--color-ink, #1a1815); }
.book-nav a[aria-current="true"] {
  background: color-mix(in srgb, var(--color-hair, #e5e0d8) 45%, transparent);
}
.book-nav__num { flex: none; width: 1.5rem; color: var(--color-accent, #b55e2a); }
.book-nav__page { margin-left: auto; color: var(--color-ink-soft, #6b6560); }
.book-nav__download {
  margin-top: 1rem;
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  color: var(--color-accent, #b55e2a);
  text-decoration: none;
}
.book-nav__download:hover { color: var(--color-ink, #1a1815); }
.book-nav__toggle { display: none; }

.book-frames {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
}
.book-frames__sheet { margin: 0; width: 100%; max-width: 46rem; scroll-margin-top: calc(var(--dq-nav-h) + 1rem); }
.book-frames__page {
  display: block;
  width: 100%;
  height: auto;
  background: var(--surface, #fff);
  border: 1px solid var(--color-hair, #e5e0d8);
  box-shadow: 0 1px 1px var(--hair), 0 10px 30px var(--hair);
}

/* Each page exists twice, printed once per theme, so nothing here colours it:
   the reader swaps the source and the sheet is already the theme's own paper
   and ink. */
[data-theme="dark"] .book-frames__page {
  border-color: var(--hair, rgba(255, 255, 255, 0.09));
  box-shadow: none;
}
@media (max-width: 1023px) {
  .book-shell { grid-template-columns: minmax(0, 1fr); gap: 1rem; }
  .book-nav {
    position: sticky;
    top: var(--dq-nav-h);
    z-index: 2;
    max-height: none;
    overflow: visible;
    background: var(--bg, #fbfbf9);
    border-bottom: 1px solid var(--color-hair, #e5e0d8);
    padding-bottom: 0.5rem;
  }
  .book-nav__toggle {
    display: inline-flex;
    align-items: center;
    min-height: 2.75rem;
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.78rem;
    color: var(--color-accent, #b55e2a);
    cursor: pointer;
  }
  .book-nav ol,
  .book-nav .book-nav__download { display: none; }
  .book-nav[data-open="true"] ol { display: block; }
  .book-nav[data-open="true"] .book-nav__download { display: inline-flex; }
  .book-nav__title { display: none; }
  .book-frames__sheet { max-width: 100%; }
}

/* Printing this page gives the book, not the site around it. The contents, the
   header and the download link are screen furniture; the sheets already are the
   printed pages, so each one becomes a sheet of paper at A4 with no margin —
   the margin is inside the page image, where the book set it. */
@media print {
  @page { size: A4; margin: 0; }
  html, body { background: var(--bg, #fff); }
  header, footer, .dt-nav, .dt-footer, .book-nav { display: none !important; }
  /* The kit's skip link is parked off-screen with a translate; paper has no
     transforms, so it prints as a black chip on the first sheet. There is
     nothing to skip to on paper. */
  a[href="#main"] { display: none !important; }
  .book-root { padding: 0 !important; }
  .book-root > div { max-width: none !important; margin: 0 !important; padding: 0 !important; }
  .book-shell { display: block; max-width: none; margin: 0; padding: 0; }
  .book-frames { display: block; gap: 0; }
  .book-frames__sheet {
    max-width: none;
    width: 100%;
    margin: 0;
    break-after: page;
    break-inside: avoid;
  }
  .book-frames__sheet:last-of-type { break-after: auto; }
  .book-frames__page { border: 0; box-shadow: none; filter: none !important; }
}
`;
