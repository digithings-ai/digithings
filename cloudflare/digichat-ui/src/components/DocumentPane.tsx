"use client";

import { MiniMarkdown } from "./MiniMarkdown";
import { readableSnippet } from "../activity-view";
import type { VaultHitSummary } from "../types";

function isHttpUrl(path: string): boolean {
  return /^https?:\/\//i.test(path);
}

function isPdfPath(path: string): boolean {
  return /\.pdf(\?|#|$)/i.test(path);
}

/**
 * Side pane for an original document (#3419). Paths without an http(s) URL
 * never become links — vault notes render from `body` loaded via get_note.
 */
export function DocumentPane({
  hit,
  onClose,
}: {
  hit: VaultHitSummary;
  onClose: () => void;
}) {
  const http = isHttpUrl(hit.path);
  const pdf = http && isPdfPath(hit.path);
  const markdown = hit.body?.trim() || "";
  return (
    <aside className="dc-doc-pane" aria-label="Document">
      <header className="dc-doc-pane-head">
        <strong className="dc-doc-pane-title">{hit.title}</strong>
        <button type="button" className="dc-doc-pane-close" onClick={onClose} aria-label="Close document">
          ×
        </button>
      </header>
      {http ? (
        <p className="dc-doc-pane-path">
          <a href={hit.path} target="_blank" rel="noreferrer noopener">
            Download
          </a>
        </p>
      ) : hit.path && hit.path !== hit.title ? (
        <p className="dc-doc-pane-path">{hit.path}</p>
      ) : null}
      {pdf ? (
        <object data={hit.path} type="application/pdf" className="dc-doc-pane-frame" title={hit.title}>
          <p>PDF preview is unavailable in this browser.</p>
        </object>
      ) : markdown ? (
        <div className="dc-doc-pane-body">
          <MiniMarkdown text={markdown} />
        </div>
      ) : hit.snippet ? (
        <p className="dc-doc-pane-snippet">{readableSnippet(hit.snippet)}</p>
      ) : (
        <p className="dc-doc-pane-empty">No preview available.</p>
      )}
    </aside>
  );
}
