"use client";

import { DocsArticle } from "@/components/docs/docs-article";
import { DocsAssistant } from "@/components/docs/docs-assistant";
import { DocsNav } from "@/components/docs/docs-nav";
import { useIsMobile } from "@/hooks/use-mobile";
import { useDocsConfig } from "@/lib/docs/config-provider";
import { getPageById } from "@/lib/docs/mock-tools";
import { BookOpenIcon, SearchIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export function DocsApp({ previewWarning }: { previewWarning?: string }) {
  const { assistant, hostUi } = useDocsConfig();
  const shell = hostUi.root.props;
  const pages = shell.pages;
  const isMobile = useIsMobile();
  const desktopAssistantPlacement = shell.assistantPlacement ?? "sidebar";
  const showAssistantAsModal = isMobile || desktopAssistantPlacement === "modal";
  const showAssistantSidebar = !showAssistantAsModal;
  const contentRef = useRef<HTMLElement>(null);
  const defaultPageId = shell.defaultPageId;
  const [selectedPageId, setSelectedPageId] = useState(defaultPageId);
  const currentPage = getPageById(selectedPageId, pages, defaultPageId);
  useEffect(() => {
    const readPageFromUrl = () => {
      const pageId = new URLSearchParams(window.location.search).get("page");
      if (pageId && pages.some((page) => page.id === pageId)) {
        setSelectedPageId(pageId);
      }
    };

    readPageFromUrl();
    window.addEventListener("popstate", readPageFromUrl);
    return () => window.removeEventListener("popstate", readPageFromUrl);
  }, [pages]);

  const handleSelectPage = (pageId: string) => {
    if (!pages.some((page) => page.id === pageId)) return;
    setSelectedPageId(pageId);
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("page", pageId);
    window.history.replaceState(null, "", nextUrl);
    requestAnimationFrame(() => {
      contentRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    });
  };

  return (
    <div className="h-dvh overflow-hidden bg-[color-mix(in_oklab,var(--docs-accent)_4%,#f7f8fb)] text-foreground">
      {previewWarning ? (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">
          {previewWarning}
        </div>
      ) : null}
      <header className="sticky top-0 z-30 border-b bg-white/95 backdrop-blur">
        <div className="flex h-14 items-center justify-between gap-4 px-4 lg:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-[var(--docs-accent)] text-[var(--docs-accent-foreground)]">
              <BookOpenIcon className="size-4" />
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{shell.productName}</div>
              <div className="truncate text-xs text-muted-foreground">{shell.docsName}</div>
            </div>
          </div>
          <div className="hidden min-w-48 items-center gap-2 rounded-md border border-[var(--docs-border)] bg-[var(--docs-accent-softer)] px-3 py-1.5 text-sm text-[var(--docs-muted)] md:flex">
            <SearchIcon className="size-4 text-[var(--docs-accent)]" />
            {assistant.labels.headerSearch}
          </div>
        </div>
      </header>

      <main
        className={`grid h-[calc(100dvh-3.5rem)] grid-cols-1 overflow-hidden ${
          showAssistantSidebar
            ? "md:grid-cols-[minmax(0,1fr)_410px] xl:grid-cols-[240px_minmax(0,1fr)_410px]"
            : "xl:grid-cols-[240px_minmax(0,1fr)]"
        }`}
      >
        <aside className="hidden h-full overflow-hidden border-r bg-white xl:block">
          <DocsNav currentPageId={currentPage.id} onSelectPage={handleSelectPage} />
        </aside>
        <section ref={contentRef} className="min-w-0 overflow-y-auto">
          <div className="border-b bg-white px-4 py-3 xl:hidden">
            <DocsNav currentPageId={currentPage.id} onSelectPage={handleSelectPage} compact />
          </div>
          <DocsArticle key={currentPage.id} page={currentPage} onSelectPage={handleSelectPage} />
        </section>
        <aside
          className={`${showAssistantSidebar ? "hidden md:block" : "hidden"} h-full min-h-0 overflow-hidden border-l bg-white`}
        >
          <DocsAssistant currentPage={currentPage} onSelectPage={handleSelectPage} mode="sidebar" />
        </aside>
      </main>

      {showAssistantAsModal ? (
        <DocsAssistant
          currentPage={currentPage}
          defaultOpen={!isMobile && desktopAssistantPlacement === "modal"}
          onSelectPage={handleSelectPage}
          mode="modal"
        />
      ) : null}
    </div>
  );
}
