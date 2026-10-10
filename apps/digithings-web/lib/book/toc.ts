/**
 * The book's table of contents (DIG-2821).
 *
 * Two levels of table of contents, built by one pure function each, because
 * both are read by three renderers that must agree:
 *
 *   - the book index (`/book`)      → the chapter list
 *   - a chapter page's side rail    → that chapter's headings
 *   - the printed book              → the same chapter list, with page numbers
 *                                    filled in by Paged.js at print time
 *
 * Page numbers are deliberately absent from this model. A page number is only
 * knowable once the document is paginated, and paginating is what the PDF step
 * does; inventing one here would put a number in the HTML that is wrong until
 * Paged.js rewrites it. The ToC therefore ships an anchor per entry, and the
 * print step replaces the label with the resolved page.
 */

import type { Heading } from "./headings";

export interface TocEntry {
  /** The heading id this entry links to. */
  id: string;
  text: string;
  /** Heading level, used for indentation and for the print stylesheet. */
  level: number;
}

export interface TocNode extends TocEntry {
  children: TocNode[];
}

export interface ChapterRef {
  slug: string;
  title: string;
  summary: string;
  order: number;
  href: string;
  /** Heading count, so the index can say how long a chapter is. */
  headingCount: number;
}

/** The URL of a chapter page. `trailingSlash: true` in next.config needs it. */
export function chapterHref(slug: string): string {
  return `/book/${slug}/`;
}

/**
 * Flatten headings to table-of-contents entries.
 *
 * Only levels 2–4 become entries. A level-1 heading is the chapter title, which
 * the page already renders as its `<h1>`, and anything deeper is a sub-clause
 * that would turn the rail into a wall of links.
 */
export function tocEntries(headings: readonly Heading[], minLevel = 2, maxLevel = 4): TocEntry[] {
  return headings
    .filter((h) => h.level >= minLevel && h.level <= maxLevel)
    .map((h) => ({ id: h.id, text: h.text, level: h.level }));
}

/**
 * Nest flat entries by heading level.
 *
 * A level jump upward (an `h2` followed by an `h4`) is legal markdown and does
 * not break the tree: the orphan is attached at the level it declares rather
 * than dropped, because a dropped entry is a link that appears in the page and
 * nowhere in the rail.
 */
export function nestToc(entries: readonly TocEntry[]): TocNode[] {
  const roots: TocNode[] = [];
  // stack[i] is the deepest open node at level i.
  const stack: TocNode[] = [];
  for (const entry of entries) {
    const node: TocNode = { ...entry, children: [] };
    while (stack.length && stack[stack.length - 1].level >= node.level) stack.pop();
    if (stack.length === 0) roots.push(node);
    else stack[stack.length - 1].children.push(node);
    stack.push(node);
  }
  return roots;
}

/** The chapter list for the book index, ordered by `order` then slug. */
export function orderChapters<T extends { slug: string; order: number }>(chapters: readonly T[]): T[] {
  return [...chapters].sort((a, b) => (a.order !== b.order ? a.order - b.order : a.slug.localeCompare(b.slug)));
}

/**
 * Previous/next links for the chapter nav.
 *
 * Takes the ordered chapter list and returns the neighbours of `slug`, or null
 * at either end — the nav renders "first"/"last" without a link rather than a
 * dead target.
 */
export function chapterNeighbours(
  chapters: readonly ChapterRef[],
  slug: string,
): { previous: ChapterRef | null; next: ChapterRef | null } {
  const at = chapters.findIndex((c) => c.slug === slug);
  if (at === -1) return { previous: null, next: null };
  return {
    previous: at > 0 ? chapters[at - 1] : null,
    next: at < chapters.length - 1 ? chapters[at + 1] : null,
  };
}