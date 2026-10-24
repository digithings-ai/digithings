/**
 * Page navigation for the web edition of the book.
 *
 * `/book` reads like the PDF: one sheet per printed page group, in the same
 * order, walked with the arrow keys or by scrolling. The rules live here, away
 * from the DOM, so they can be tested without a browser.
 */

export interface ReaderPage {
  /** Element id of the sheet, also the URL hash. */
  id: string;
  /** Number shown in the contents and on the sheet; empty for cover and closing. */
  number: string;
  title: string;
}

/** The page `delta` steps from `current`, clamped to the book. */
export function stepPage(
  pages: readonly ReaderPage[],
  current: string,
  delta: number,
): ReaderPage | null {
  if (pages.length === 0) return null;
  const index = pages.findIndex((page) => page.id === current);
  const from = index < 0 ? 0 : index;
  const to = Math.min(pages.length - 1, Math.max(0, from + delta));
  return pages[to] ?? null;
}

/** Arrow-key direction, or 0 when the key is not a page turn. */
export function pageDelta(event: {
  key: string;
  altKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
}): number {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return 0;
  if (event.key === "ArrowRight") return 1;
  if (event.key === "ArrowLeft") return -1;
  return 0;
}

/** Keys typed into a field, a select or an editable region are not page turns. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!target || typeof (target as Element).closest !== "function") return false;
  return Boolean(
    (target as Element).closest(
      "input, textarea, select, [contenteditable=''], [contenteditable='true']",
    ),
  );
}
