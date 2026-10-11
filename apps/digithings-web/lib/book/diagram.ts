/**
 * Mermaid fences -> one static SVG, shared by the web page and the PDF
 * (DIG-2821).
 *
 * The brief's requirement is "the same SVG used in PDF", and the only way to
 * make that true by construction rather than by discipline is to give a
 * diagram exactly one address. A mermaid fence becomes:
 *
 *   1. a content-addressed id, `sha256(normalised source).slice(0, 16)`
 *   2. a single file at `public/book/diagrams/<id>.svg`, written at build time
 *   3. an `<img src="/book/diagrams/<id>.svg">` in the exported HTML
 *
 * The web page and the printed page therefore load the same URL from the same
 * export — there is no second render, no server-side mermaid call at request
 * time, and no way for the two to drift. Editing a diagram changes its id, so a
 * stale SVG can never be served under an unchanged name.
 *
 * Normalisation matters for the hash: mermaid treats trailing whitespace and
 * `\r\n` as insignificant, so two files that render identically must not
 * produce two SVGs. Indentation is NOT normalised — it carries diagram layout.
 */

import { createHash } from "node:crypto";

import { DIAGRAM_PUBLIC_DIR, DIAGRAM_URL_PREFIX, diagramFile, diagramUrl } from "./diagramPaths.ts";

export { DIAGRAM_PUBLIC_DIR, DIAGRAM_URL_PREFIX, diagramFile, diagramUrl };

/** Fence languages this reader treats as a diagram. */
export const DIAGRAM_LANGS = ["mermaid", "mmd"] as const;

/** A mermaid fence lifted out of a chapter body. */
export interface DiagramSource {
  /** The fence's raw mermaid source, trimmed. */
  source: string;
  /** Content-addressed id — the file name and the URL slug. */
  id: string;
  /** `/book/diagrams/<id>.svg` — what both the web page and the PDF load. */
  url: string;
  /** `book/diagrams/<id>.svg` — the write target, relative to `public/`. */
  file: string;
}

const CR = /\r\n?/g;

/**
 * Canonical form used for the content hash.
 *
 * Line endings and trailing whitespace are dropped because they do not change
 * the rendered diagram; internal indentation is kept because it does.
 */
export function normalizeDiagramSource(source: string): string {
  return source
    .replace(CR, "\n")
    .split("\n")
    .map((line) => line.replace(/[ \t]+$/, ""))
    .join("\n")
    .replace(/\n+$/, "");
}

/** The content-addressed id for a mermaid source. Stable across runs and hosts. */
export function diagramId(source: string): string {
  return createHash("sha256").update(normalizeDiagramSource(source), "utf8").digest("hex").slice(0, 16);
}

/** A diagram's id, url and write path, all derived from its source. */
export function describeDiagram(source: string): DiagramSource {
  const id = diagramId(source);
  return { source: source.trim(), id, url: diagramUrl(id), file: diagramFile(id) };
}

/**
 * A mermaid fence found in a chapter body.
 *
 * `index` is the fence's zero-based position among the chapter's diagrams and
 * is what makes the figure caption stable ("Figure 3") without counting the
 * headings between them.
 */
export interface DiagramFence {
  index: number;
  source: string;
}

/**
 * Collect every mermaid fence in a body, in document order.
 *
 * The scan is line-based and fence-aware: a ``` inside a longer fence cannot
 * close it early, and an unterminated fence is reported rather than skipped, so
 * a typo cannot silently drop a diagram from the book.
 */
export function findDiagramFences(body: string): DiagramFence[] {
  const lines = body.replace(CR, "\n").split("\n");
  const out: DiagramFence[] = [];
  let i = 0;
  while (i < lines.length) {
    const open = /^(\s*)(`{3,}|~{3,})\s*([A-Za-z0-9_+-]*)\s*$/.exec(lines[i]);
    if (!open) {
      i += 1;
      continue;
    }
    const marker = open[2];
    const lang = open[3].toLowerCase();
    const body_start = i + 1;
    let close = -1;
    for (let j = body_start; j < lines.length; j++) {
      const c = new RegExp(`^\\s*${marker[0] === "`" ? "`" : "~"}{${marker.length},}\\s*$`).exec(lines[j]);
      if (c) {
        close = j;
        break;
      }
    }
    if (close === -1) {
      throw new Error(`unterminated \`\`\`${lang || ""} fence opened on line ${i + 1}`);
    }
    if ((DIAGRAM_LANGS as readonly string[]).includes(lang)) {
      out.push({ index: out.length, source: lines.slice(body_start, close).join("\n") });
    }
    i = close + 1;
  }
  return out;
}

/**
 * How a chapter's mermaid fences are rewritten for rendering.
 *
 * The replacement is a plain Markdown image, not a JSX component: an `<img>`
 * needs no client bundle, prints identically under Paged.js and Playwright, and
 * carries the one address both outputs share. A caption is written as the
 * figure's own alt text, so a screen reader and a printed page say the same
 * thing.
 */
export function diagramMarkdown(fence: DiagramFence, caption?: string): string {
  const d = describeDiagram(fence.source);
  const alt = caption ? caption.replace(/\n/g, " ").trim() : `diagram ${fence.index + 1}`;
  return `![${alt}](${d.url})`;
}

