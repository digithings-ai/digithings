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
  background: #fff;
  border: 1px solid var(--color-hair, #e5e0d8);
  box-shadow: 0 1px 1px rgba(26, 24, 21, 0.04), 0 10px 30px rgba(26, 24, 21, 0.07);
}

@media (max-width: 1023px) {
  .book-shell { grid-template-columns: minmax(0, 1fr); gap: 1rem; }
  .book-nav {
    position: sticky;
    top: var(--dq-nav-h);
    z-index: 2;
    max-height: none;
    overflow: visible;
    background: var(--color-paper, #faf7f2);
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
`;
