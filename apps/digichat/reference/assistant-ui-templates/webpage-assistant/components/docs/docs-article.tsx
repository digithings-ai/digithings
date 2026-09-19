"use client";

import { MarkdownPage } from "@/components/docs/markdown-page";
import { Button } from "@/components/ui/button";
import { useDocsConfig } from "@/lib/docs/config-provider";
import { getPageById } from "@/lib/docs/mock-tools";
import type { DocsPage } from "@/lib/docs/types";
import { ArrowRightIcon, FileTextIcon } from "lucide-react";

export function DocsArticle({
  page,
  onSelectPage,
}: {
  page: DocsPage;
  onSelectPage: (pageId: string) => void;
}) {
  const { hostUi } = useDocsConfig();
  const related = page.relatedPageIds.map((pageId) =>
    getPageById(pageId, hostUi.root.props.pages, hostUi.root.props.defaultPageId),
  );

  return (
    <article className="mx-auto max-w-4xl px-4 py-8 lg:px-10">
      <PageHeader page={page} />
      <MarkdownPage markdown={page.markdown} />
      <RelatedPages related={related} onSelectPage={onSelectPage} />
      <ArticleCta />
    </article>
  );
}

function PageHeader({ page }: { page: DocsPage }) {
  const { assistant } = useDocsConfig();

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="rounded-full border bg-white px-2.5 py-1">{page.section}</span>
        <span className="rounded-full bg-[var(--docs-accent-soft)] px-2.5 py-1 text-[var(--docs-accent)]">
          {assistant.labels.currentPage}: {page.title}
        </span>
      </div>
      <h1 className="text-3xl font-semibold tracking-normal text-slate-950 md:text-4xl">
        {page.title}
      </h1>
      <p className="mt-3 max-w-2xl text-base leading-7 text-muted-foreground">{page.description}</p>
    </>
  );
}

function RelatedPages({
  related,
  onSelectPage,
}: {
  related: DocsPage[];
  onSelectPage: (pageId: string) => void;
}) {
  const { assistant } = useDocsConfig();
  const uniqueRelated = related.filter(
    (page, index, pages) => pages.findIndex((item) => item.id === page.id) === index,
  );

  if (uniqueRelated.length === 0) return null;

  return (
    <div className="mt-10 border-t pt-6">
      <h2 className="mb-3 text-sm font-semibold text-slate-900">{assistant.labels.relatedPages}</h2>
      <div className="grid gap-3">
        {uniqueRelated.map((relatedPage) => (
          <button
            key={relatedPage.id}
            type="button"
            onClick={() => onSelectPage(relatedPage.id)}
            className="rounded-lg border bg-white p-4 text-left transition-colors hover:border-[var(--docs-accent)] hover:bg-[var(--docs-accent-softer)]"
          >
            <div className="flex items-start gap-3">
              <FileTextIcon className="mt-0.5 size-4 shrink-0 text-[var(--docs-accent)]" />
              <div className="min-w-0">
                <div className="font-medium">{relatedPage.title}</div>
                <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                  {relatedPage.description}
                </p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function ArticleCta() {
  const { assistant } = useDocsConfig();

  return (
    <div className="mt-10 rounded-lg border bg-white p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="font-medium">{assistant.labels.articleCtaTitle}</div>
          <p className="text-sm text-muted-foreground">{assistant.labels.articleCtaBody}</p>
        </div>
        <Button variant="outline" className="w-full gap-1.5 sm:w-auto">
          {assistant.labels.articleCtaAction}
          <ArrowRightIcon className="size-4" />
        </Button>
      </div>
    </div>
  );
}
