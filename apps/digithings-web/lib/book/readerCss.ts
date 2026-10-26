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
  color: var(--accent);
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
.book-nav__num { flex: none; width: 1.5rem; color: var(--accent); }
.book-nav__page { margin-left: auto; color: var(--color-ink-soft, #6b6560); }

/* Export: one boxed cell per format, under the contents. The cells are drawn
   only with hairlines and ink, so they read as part of the contents list
   rather than as site chrome — and they repaint with the theme like the book
   beside them. */
.book-export {
  margin-top: 1.25rem;
  padding-top: 0.85rem;
  border-top: 1px solid var(--hair, rgba(20, 24, 27, 0.12));
}
.book-export__title {
  margin: 0 0 0.6rem;
  font-size: 0.72rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
}
.book-export__row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.4rem;
}
.book-export__btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  min-height: 3.5rem;
  padding: 0.55rem 0.2rem;
  border: 1px solid var(--hair, rgba(20, 24, 27, 0.12));
  background: transparent;
  color: var(--color-ink-soft, #6b6560);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 0.68rem;
  letter-spacing: 0.1em;
  cursor: pointer;
  transition: color 120ms ease, border-color 120ms ease, background-color 120ms ease;
}
.book-export__btn:hover {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 6%, transparent);
  color: var(--ink, #1a1815);
}
.book-export__btn:active { transform: translateY(1px); }
.book-export__btn:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
.book-export__btn[data-state="done"] {
  border-color: var(--accent);
  color: var(--accent);
}
.book-export__btn[data-state="error"] { border-style: dashed; }
.book-export__btn[disabled] { opacity: 0.55; cursor: progress; }
.book-export__mark svg { display: block; width: 1.15rem; height: 1.15rem; }
.book-export__label { line-height: 1; }
.book-export__status {
  margin: 0.6rem 0 0;
  min-height: 1rem;
  font-size: 0.66rem;
  letter-spacing: 0.04em;
  color: var(--color-ink-soft, #6b6560);
}
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
  .book-shell {
    grid-template-columns: minmax(0, 1fr);
    gap: 1rem;
    /* room for the bar that stays at the foot of the screen */
    padding-bottom: calc(4.5rem + env(safe-area-inset-bottom));
  }
  /* Contents and export live in a bar at the bottom, not at the top. The top
     bar retracts as you scroll, and a sticky header pinned to its height left a
     stripe of nothing above the contents. A bar that never moves cannot. */
  .book-nav {
    position: fixed;
    inset: auto 0 0 0;
    min-width: 0;
    z-index: 40;
    display: grid;
    /* Export on the left, contents on the right: the right edge is where a
       right-handed thumb lands. Areas, so the two cannot land on separate
       rows when the text grows. */
    grid-template-areas: "export toggle";
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.6rem;
    max-height: none;
    overflow: visible;
    padding: 0.5rem var(--gutter) calc(0.5rem + env(safe-area-inset-bottom));
    background: var(--bg, #fbfbf9);
    border-top: 1px solid var(--hair, #e5e0d8);
    border-bottom: 0;
  }
  /* A bordered pill with the chapter you are in, the way a reader thinks of
     where they are — not a word that says "contents" and nothing else. */
  .book-nav__toggle {
    grid-area: toggle;
    justify-self: end;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    max-width: 100%;
    min-height: 2.5rem;
    padding: 0 0.6rem;
    border: 1px solid var(--hair, #e5e0d8);
    border-radius: 2px;
    background: var(--surface, transparent);
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: 0.72rem;
    color: var(--ink);
    cursor: pointer;
  }
  .book-nav__toggle-num { flex: none; color: var(--accent); }
  .book-nav__toggle-text {
    min-width: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .book-nav__chevron {
    flex: none;
    width: 0.7rem;
    height: 0.7rem;
    color: var(--ink-soft);
    transition: transform 150ms ease;
  }
  .book-nav[data-open="true"] .book-nav__chevron { transform: rotate(180deg); }
  /* The list opens upward from the bar, over the page. */
  .book-nav ol {
    display: none;
    position: absolute;
    bottom: calc(100% + 1px);
    left: 0;
    right: 0;
    max-height: 60vh;
    overflow: auto;
    margin: 0;
    padding: 0.5rem var(--gutter) 0.75rem;
    background: var(--bg, #fbfbf9);
    border-top: 1px solid var(--hair, #e5e0d8);
  }
  .book-nav[data-open="true"] ol { display: block; }
  .book-nav__title { display: none; }
  /* The export stays in the bar: two compact cells, no heading. */
  .book-nav .book-export { grid-area: export; margin: 0; min-width: 0; }
  /* The bar is a control strip, not a place for progress prose. */
  .book-nav .book-export__status { display: none; }
  .book-nav .book-export__title { display: none; }
  .book-nav .book-export__row { display: flex; gap: 0.4rem; }
  .book-nav .book-export__btn {
    min-height: 2.5rem;
    padding: 0 0.7rem;
    font-size: 0.72rem;
  }
  .book-nav .book-export__mark { display: none; }
  .book-nav .book-export__row { gap: 0.3rem; }
}

/* A 320px phone cannot hold "contents" and two full-size cells side by side:
   the grid overflowed by a measured 32px, which widened the layout viewport and
   pushed the fixed bar below the fold. Tighten, do not wrap — the bar has to
   stay one line and stay put. */
@media (max-width: 420px) {
  .book-nav { padding-inline: 0.9rem; gap: 0.5rem; }
  .book-nav .book-export__btn {
    padding: 0 0.45rem;
    font-size: 0.66rem;
    min-height: 2.3rem;
  }
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
  /* The paginated source stays on the page for pagedjs, off-screen; on paper it
     would print as a second, unpaginated copy of the book. */
  .book-live__source { display: none !important; }
  .book-live { height: auto !important; overflow: visible; }
  /* Undo the reader's fit-to-column: the page boxes are already A4, and a
     scaled box prints cropped because the sheet is measured before the
     transform. */
  .book-live__stage { transform: none !important; width: 794px !important; height: auto !important; }
  .book-live .pagedjs_page {
    width: 794px !important;
    height: 1123px !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    break-after: page;
    break-inside: avoid;
  }
  .book-live .pagedjs_page:last-child { break-after: auto; }
}
`;
