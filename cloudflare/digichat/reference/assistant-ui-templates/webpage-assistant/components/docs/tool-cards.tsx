"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CheckCircle2Icon, Code2Icon, ExternalLinkIcon, FileSearchIcon } from "lucide-react";

type ToolCardProps = {
  toolName: string;
  displayName: string;
  expectedRenderer: string;
  result?: unknown;
  argsText?: string;
  status?: { type: string };
  onSelectPage?: (pageId: string) => void;
};

type SourceResults = {
  query: string;
  results: Array<{
    pageId: string;
    title: string;
    section: string;
    url: string;
    snippet: string;
    score: number;
  }>;
};

type PagePreview = {
  pageId: string;
  title: string;
  section: string;
  url: string;
  description: string;
  relatedPageIds: string[];
};

type CodeSnippet = {
  topic: string;
  language: string;
  code: string;
  notes: string[];
  docsUrl: string;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

function isSourceResults(value: unknown): value is SourceResults {
  return (
    isRecord(value) &&
    typeof value.query === "string" &&
    Array.isArray(value.results) &&
    value.results.every(
      (item) =>
        isRecord(item) &&
        typeof item.pageId === "string" &&
        typeof item.title === "string" &&
        typeof item.snippet === "string" &&
        typeof item.url === "string",
    )
  );
}

function isPagePreview(value: unknown): value is PagePreview {
  return (
    isRecord(value) &&
    typeof value.pageId === "string" &&
    typeof value.title === "string" &&
    typeof value.description === "string" &&
    typeof value.url === "string" &&
    Array.isArray(value.relatedPageIds)
  );
}

function isCodeSnippet(value: unknown): value is CodeSnippet {
  return (
    isRecord(value) &&
    typeof value.topic === "string" &&
    typeof value.language === "string" &&
    typeof value.code === "string" &&
    Array.isArray(value.notes) &&
    typeof value.docsUrl === "string"
  );
}

function ToolShell({
  icon,
  title,
  subtitle,
  children,
  muted,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  muted?: boolean;
}) {
  return (
    <div
      className={cn(
        "my-2 overflow-hidden rounded-lg border bg-white text-sm shadow-sm",
        muted && "bg-muted/30",
      )}
    >
      <div className="flex items-start gap-3 border-b bg-muted/35 px-3 py-2.5">
        <div className="mt-0.5 text-[var(--docs-accent)]">{icon}</div>
        <div className="min-w-0">
          <div className="font-medium text-foreground">{title}</div>
          {subtitle ? <div className="text-xs text-muted-foreground">{subtitle}</div> : null}
        </div>
      </div>
      <div className="space-y-2 p-3">{children}</div>
    </div>
  );
}

export function SourceResultsToolCard(props: ToolCardProps) {
  if (props.status?.type === "running" || props.result === undefined) {
    return (
      <ToolShell
        icon={<FileSearchIcon className="size-4" />}
        title={props.displayName}
        subtitle="Searching the docs index"
        muted
      >
        <div className="h-2 w-2/3 animate-pulse rounded-full bg-muted-foreground/20" />
        <div className="h-2 w-1/2 animate-pulse rounded-full bg-muted-foreground/20" />
      </ToolShell>
    );
  }

  if (!isSourceResults(props.result)) return <GenericToolCard {...props} />;

  return (
    <ToolShell
      icon={<FileSearchIcon className="size-4" />}
      title={props.displayName}
      subtitle={`Query: ${props.result.query}`}
    >
      {props.result.results.map((result) => (
        <button
          key={result.pageId}
          type="button"
          onClick={() => props.onSelectPage?.(result.pageId)}
          className="block w-full rounded-md border px-3 py-2 text-left transition-colors hover:border-[var(--docs-accent)] hover:bg-[var(--docs-accent-softer)]"
        >
          <div className="flex items-center justify-between gap-3">
            <span className="min-w-0 truncate font-medium">{result.title}</span>
            <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
              {result.section}
            </span>
          </div>
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{result.snippet}</p>
          <span className="mt-1 inline-flex items-center gap-1 text-xs text-[var(--docs-accent)]">
            <ExternalLinkIcon className="size-3" />
            {result.url}
          </span>
        </button>
      ))}
    </ToolShell>
  );
}

export function PagePreviewToolCard(props: ToolCardProps) {
  if (props.status?.type === "running" || props.result === undefined) {
    return (
      <ToolShell
        icon={<ExternalLinkIcon className="size-4" />}
        title={props.displayName}
        subtitle="Loading page metadata"
        muted
      >
        <div className="h-2 w-3/4 animate-pulse rounded-full bg-muted-foreground/20" />
      </ToolShell>
    );
  }

  if (!isPagePreview(props.result)) return <GenericToolCard {...props} />;
  const result = props.result;

  return (
    <ToolShell
      icon={<ExternalLinkIcon className="size-4" />}
      title={result.title}
      subtitle={`${result.section} / ${result.url}`}
    >
      <p className="text-muted-foreground">{result.description}</p>
      <div className="flex flex-wrap gap-1.5">
        {result.relatedPageIds.slice(0, 4).map((pageId) => (
          <span key={pageId} className="rounded-full bg-muted px-2 py-0.5 text-xs">
            {pageId}
          </span>
        ))}
      </div>
      <Button size="sm" className="h-8 gap-1.5" onClick={() => props.onSelectPage?.(result.pageId)}>
        <ExternalLinkIcon className="size-3.5" />
        Open in preview
      </Button>
    </ToolShell>
  );
}

export function CodeSnippetToolCard(props: ToolCardProps) {
  if (props.status?.type === "running" || props.result === undefined) {
    return (
      <ToolShell
        icon={<Code2Icon className="size-4" />}
        title={props.displayName}
        subtitle="Generating code"
        muted
      >
        <div className="h-2 w-5/6 animate-pulse rounded-full bg-muted-foreground/20" />
        <div className="h-2 w-2/3 animate-pulse rounded-full bg-muted-foreground/20" />
      </ToolShell>
    );
  }

  if (!isCodeSnippet(props.result)) return <GenericToolCard {...props} />;

  return (
    <ToolShell
      icon={<Code2Icon className="size-4" />}
      title={`${props.displayName}: ${props.result.language}`}
      subtitle={props.result.topic}
    >
      <pre className="max-h-72 overflow-x-auto rounded-md bg-slate-950 p-3 text-xs leading-relaxed text-slate-50">
        <code>{props.result.code}</code>
      </pre>
      <div className="space-y-1">
        {props.result.notes.map((note) => (
          <div key={note} className="flex items-start gap-1.5 text-xs text-muted-foreground">
            <CheckCircle2Icon className="mt-0.5 size-3.5 shrink-0 text-emerald-600" />
            <span>{note}</span>
          </div>
        ))}
      </div>
      <div className="text-xs text-[var(--docs-accent)]">{props.result.docsUrl}</div>
    </ToolShell>
  );
}

export function GenericToolCard(props: ToolCardProps) {
  return (
    <ToolShell
      icon={<FileSearchIcon className="size-4" />}
      title={props.displayName || props.toolName}
      subtitle={`Renderer: ${props.expectedRenderer || "generic"}`}
    >
      {props.argsText ? (
        <pre className="overflow-x-auto rounded-md bg-muted p-2 text-xs">{props.argsText}</pre>
      ) : null}
      {props.result !== undefined ? (
        <pre className="max-h-72 overflow-x-auto rounded-md bg-muted p-2 text-xs">
          {typeof props.result === "string" ? props.result : JSON.stringify(props.result, null, 2)}
        </pre>
      ) : (
        <p className="text-muted-foreground">Waiting for a tool result.</p>
      )}
    </ToolShell>
  );
}
