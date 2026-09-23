"use client";

import { memo } from "react";
import type { SourceMessagePartComponent } from "@assistant-ui/react";
import { DotMatrix } from "../DotMatrix";
import { cn } from "./cn";

/**
 * A citation source (#4552).
 *
 * Providers with a built-in web-search / grounding tool return citations, and
 * the digigraph and foundry adapters already emit `retrieve` documents. Both
 * arrive on the wire as `source-url` / `source-document` parts, which the
 * runtime converts to a single `source` part. Until this existed they fell
 * through the message part switch's `default` and were dropped, so a grounded
 * answer showed no provenance at all.
 *
 * Rendered as a compact row inline in the message: a link for a web source,
 * plain text for a document. Kept deliberately plain — the citations are
 * supporting detail, not the answer.
 */
const ThreadSourceImpl: SourceMessagePartComponent = (props) => {
  const { sourceType, title } = props;
  const isUrl = sourceType === "url";
  const detail = isUrl ? props.url : props.filename;
  const label = title?.trim() || detail?.trim() || "Source";

  const rowClass = cn(
    "aui-source-row text-muted-foreground hover:text-foreground inline-flex max-w-full items-center gap-2 py-0.5 text-sm transition-colors",
  );

  const inner = (
    <>
      <DotMatrix
        state="searching"
        label="Source"
        className="aui-source-mark size-3.5 shrink-0"
      />
      <span className="aui-source-label min-w-0 truncate">{label}</span>
    </>
  );

  if (isUrl) {
    return (
      <a
        data-slot="aui_source-url"
        href={props.url}
        target="_blank"
        rel="noreferrer noopener"
        className={rowClass}
      >
        {inner}
      </a>
    );
  }

  return (
    <span data-slot="aui_source-document" className={rowClass}>
      {inner}
    </span>
  );
};

ThreadSourceImpl.displayName = "ThreadSource";

export const ThreadSource = memo(ThreadSourceImpl);
