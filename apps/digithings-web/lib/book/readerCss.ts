/**
 * Screen styles for `/book`, the paginated book (DIG-2821 follow-up).
 *
 * The page shows the book's own paginated document — the same one the PDF is
 * printed from — scaled to the column. It is not a set of images: the site's
 * tokens live on `<html>` and pagedjs copies them into every page box, so the
 * book follows the reader's theme and palette, all of them, and repaints when
 * the theme changes.
 *
 * Nothing here sets a colour. Paper, ink, accent and rules come from the theme.
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

/* The print sheet hides every nav element on the route so printed paper carries no
   site chrome; the contents here is a nav too. Same importance, higher
   specificity, so the reader keeps its contents and paper still loses it. */
.book-shell .book-nav { display: block !important; }
.book-nav {
  position: sticky;
  top: calc(var(--dq-nav-h) + 1.5rem);
  align-self: start;
  max-height: calc(100dvh - var(--dq-nav-h) - 3rem);
  overflow: auto;
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.78rem;
}
.book-nav__title {
  margin: 0 0 0.75rem;
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
  align-items: baseline;
  padding: 0.45rem 0;
  color: var(--color-ink-soft, #6b6560);
  text-decoration: none;
}
.book-nav a[aria-current="true"] { color: var(--color-ink, #1a1815); }
.book-nav a[aria-current="true"] .book-nav__num {
  background: color-mix(in srgb, var(--color-hair, #e5e0d8) 45%, transparent);
}
.book-nav__num { flex: none; width: 1.5rem; color: var(--color-accent, #b55e2a); }
.book-nav__page { margin-left: auto; color: var(--color-ink-soft, #6b6560); }
.book-nav__download {
  display: inline-flex;
  margin-top: 1rem;
  min-height: 2.75rem;
  align-items: center;
  color: var(--color-accent, #b55e2a);
  text-decoration: none;
}
.book-nav__download:hover { color: var(--color-ink, #1a1815); }
.book-nav__toggle { display: none; }

/* The document is laid out at A4 (794px), then scaled to the column. The
   wrapper carries the scaled height so the page scrolls to the right length;
   the stage keeps its real width so the pagination never depends on the
   window. */
.book-live {
  position: relative;
  width: 100%;
  overflow: hidden;
}
.book-live__stage {
  transform-origin: top left;
}
.book-live__source {
  position: absolute;
  left: -10000px;
  top: 0;
  /* The same width the PDF is paginated at. pagedjs reflows into A4 page
     boxes, but figures are measured against their container before that
     happens; a narrower source fitted the use-cases chapter onto one page
     where the printed book gives it two. */
  width: 1280px;
}
.book-live .pagedjs_pages { margin: 0; }
/* A page is separated from the next by a rule above and a rule below, not by a
   card: the paper is the page, and a frame around it draws a second edge that
   the book itself does not have. The pair reads as the gutter between two
   sheets, and both lines take the theme's hairline colour. */
.book-live .pagedjs_page {
  margin: 0 0 2.25rem;
  padding: 1.1rem 0;
  border: 0;
  border-top: 1px solid var(--hair, rgba(20, 24, 27, 0.12));
  border-bottom: 1px solid var(--hair, rgba(20, 24, 27, 0.12));
  box-shadow: none;
  background: transparent;
}
.book-live .pagedjs_page:last-child { margin-bottom: 0; }

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
}

/* Printing this page gives the book, not the site around it. The pages are
   already A4 and already the printed artefact, so they print at their own size
   and break once per sheet — the margins are inside the page, where the book
   set them. */
@media print {
  @page { size: A4; margin: 0; }
  html, body { background: var(--bg, #fff); }
  header, footer, .dt-nav, .dt-footer, .book-shell .book-nav { display: none !important; }
  /* The kit's skip link is parked off-screen with a translate; paper has no
     transforms, so it prints as a black chip on the first sheet. There is
     nothing to skip to on paper. */
  a[href="#main"] { display: none !important; }
  .book-root { padding: 0 !important; }
  .book-root > div { max-width: none !important; margin: 0 !important; padding: 0 !important; }
  .book-shell { display: block; max-width: none; margin: 0; padding: 0; }
  .book-live { height: auto !important; overflow: visible; }
  .book-live__stage { transform: none !important; width: auto !important; }
  .book-live .pagedjs_page { margin: 0 !important; break-after: page; break-inside: avoid; }
  .book-live .pagedjs_page:last-child { break-after: auto; }
}
`;
