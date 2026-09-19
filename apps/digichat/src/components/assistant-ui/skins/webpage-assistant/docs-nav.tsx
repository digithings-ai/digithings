"use client";

import { useDocsConfig } from "./config-provider";
import { cn } from "@/lib/utils";

export function DocsNav({
  currentPageId,
  onSelectPage,
  compact = false,
}: {
  currentPageId: string;
  onSelectPage: (pageId: string) => void;
  compact?: boolean;
}) {
  const { hostUi } = useDocsConfig();
  const pages = hostUi.root.props.pages;
  const selectPage = (pageId: string) => {
    onSelectPage(pageId);
  };
  const navGroups =
    hostUi.root.props.navGroups ??
    Array.from(new Set(pages.map((page) => page.section))).map((section) => ({
      label: section,
      pageIds: pages.filter((page) => page.section === section).map((page) => page.id),
    }));

  if (compact) {
    return (
      <select
        className="w-full rounded-md border bg-white px-3 py-2 text-sm"
        value={currentPageId}
        onChange={(event) => selectPage(event.currentTarget.value)}
        onInput={(event) => selectPage(event.currentTarget.value)}
        aria-label="Select docs page"
      >
        {pages.map((page) => (
          <option key={page.id} value={page.id}>
            {page.section}: {page.title}
          </option>
        ))}
      </select>
    );
  }

  return (
    <nav className="h-full overflow-y-auto px-4 py-5">
      {navGroups.map((group) => {
        const groupPages = group.pageIds
          .map((pageId) => pages.find((page) => page.id === pageId))
          .filter((page) => page !== undefined);

        if (groupPages.length === 0) return null;

        return (
          <div key={group.label} className="mb-6">
            <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {group.label}
            </div>
            <div className="space-y-1">
              {groupPages.map((page) => (
                <button
                  key={page.id}
                  type="button"
                  onClick={() => selectPage(page.id)}
                  className={cn(
                    "block w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors",
                    currentPageId === page.id
                      ? "bg-[var(--docs-accent-soft)] font-medium text-[var(--docs-accent)]"
                      : "text-[var(--docs-muted)] hover:bg-[var(--docs-accent-softer)] hover:text-foreground",
                  )}
                >
                  {page.title}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </nav>
  );
}
