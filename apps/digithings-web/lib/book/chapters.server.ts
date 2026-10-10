/**
 * Reading the book off disk (DIG-2821).
 *
 * The `.server` suffix is the whole guard: this module touches `node:fs`, so it
 * must never be pulled into a client bundle by a component that only wanted the
 * chapter's metadata. Next enforces the suffix; the `server-only` package is
 * deliberately NOT imported, because it is not a dependency of this app and
 * adding the import would break the very build that has to run this file.
 *
 * Everything below is resolved at BUILD time. `output: "export"` means the
 * published site is a directory of HTML: there is no server to read a chapter
 * later, and that is the reason the whole book is a build step rather than a
 * route handler.
 *
 * Plain TypeScript with type annotations only, so the build step
 * (`scripts/book/render-diagrams.mjs`) imports these same modules directly
 * through Node's type stripping. One source of truth for the addresses.
 */

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describeDiagram, findDiagramFences, type DiagramSource } from "./diagram.ts";
import { extractHeadings, type Heading } from "./headings.ts";
import { parseFrontmatter, splitFrontmatter } from "./frontmatter.ts";
import { chapterHref, orderChapters, tocEntries, type ChapterRef, type TocEntry } from "./toc.ts";

export interface Chapter extends ChapterRef {
  /** Every heading, including the level-1 title, for the chapter rail. */
  headings: Heading[];
  /** The rail's entries, already filtered to levels 2–4. */
  toc: TocEntry[];
  /** Every diagram in the chapter, resolved to its one shared address. */
  diagrams: DiagramSource[];
  /** `true` keeps a chapter out of the ToC, the nav and the printed book. */
  draft: boolean;
}

/** Where chapters live, relative to the app root. */
export const BOOK_CONTENT_DIR = "content/book";

/**
 * The file name is the slug: `03-build-and-print.mdx` → `03-build-and-print`.
 * Authors order with `order:` in the header, not with the file name, so the
 * slug stays stable when a chapter moves in the book.
 */
export function slugFromFileName(fileName: string): string {
  return fileName.replace(/\.mdx?$/, "");
}

/** Read and parse one chapter file. */
export function loadChapter(path: string, name = path): Chapter {
  const source = readFileSync(path, "utf8");
  const { yaml, body } = splitFrontmatter(source);
  const meta = parseFrontmatter(yaml, name);
  const slug = slugFromFileName(name);
  const fences = findDiagramFences(body);
  const diagrams = fences.map((f) => describeDiagram(f.source));
  const headings = extractHeadings(body);
  const toc = tocEntries(headings);
  return {
    slug,
    title: meta.title,
    summary: meta.summary,
    order: meta.order,
    headingCount: toc.length,
    href: chapterHref(slug),
    headings,
    toc,
    diagrams,
    draft: meta.draft,
  };
}

/** Read and parse every chapter, ordered, drafts removed. */
export function loadChapters(root: string): Chapter[] {
  const dir = join(root, BOOK_CONTENT_DIR);
  let files: string[];
  try {
    files = readdirSync(dir).filter((f) => /\.mdx?$/.test(f));
  } catch {
    // An empty book is a valid state (the branch that adds the toolchain
    // before the first chapter lands). The index renders an empty ToC; it
    // does not crash the whole site build.
    return [];
  }
  const chapters = files.map((file) => loadChapter(join(dir, file), file));
  return orderChapters(chapters).filter((c) => !c.draft);
}

/** The chapter list the book index and the chapter nav share. */
export function chapterRefs(chapters: readonly Chapter[]): ChapterRef[] {
  return orderChapters(chapters).map((c) => ({
    slug: c.slug,
    title: c.title,
    summary: c.summary,
    order: c.order,
    href: c.href,
    headingCount: c.headingCount,
  }));
}

/** Every diagram across the book, de-duplicated by id. */
export function allDiagrams(chapters: readonly Chapter[]): DiagramSource[] {
  const byId = new Map<string, DiagramSource>();
  for (const chapter of chapters) {
    for (const diagram of chapter.diagrams) byId.set(diagram.id, diagram);
  }
  return [...byId.values()].sort((a, b) => a.id.localeCompare(b.id));
}