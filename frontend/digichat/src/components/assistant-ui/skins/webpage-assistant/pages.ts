import type { DocsPage } from "./types";

export function getPageById(pageId: string | undefined, pages: DocsPage[], defaultPageId?: string) {
  return (
    pages.find((page) => page.id === pageId) ??
    pages.find((page) => page.id === defaultPageId) ??
    pages[0]
  );
}
