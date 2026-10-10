/**
 * Reading the book off disk (DIG-2821).
 *
 * Layout (owner rule 2026-10-11: every section is its own page):
 *
 *   content/book/<NN-chapter>/index.mdx      chapter opener: title, order,
 *                                            summary, a short introduction
 *   content/book/<NN-chapter>/<NN-topic>.mdx one section = one page at
 *                                            /book/<chapter>/<topic>/
 *
 * The directory name is the chapter slug and the file name the section slug;
 * order comes from each file's `order:` header so a rename never reorders the
 * book. Server-only (`node:fs`), resolved at build time for `output: "export"`.
 * Plain TypeScript so the build scripts import the same module through Node's
 * type stripping.
 */

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describeDiagram, findDiagramFences, type DiagramSource } from "./diagram.ts";
import { extractHeadings, type Heading } from "./headings.ts";
import { parseFrontmatter, splitFrontmatter } from "./frontmatter.ts";
import {
  chapterHref,
  orderChapters,
  sectionHref,
  tocEntries,
  type ChapterWithSections,
  type SectionRef,
  type TocEntry,
} from "./toc.ts";

export interface Section extends SectionRef {
  headings: Heading[];
  toc: TocEntry[];
  diagrams: DiagramSource[];
  draft: boolean;
}

export interface Chapter extends ChapterWithSections {
  /** The opener's own headings (usually none). */
  headings: Heading[];
  toc: TocEntry[];
  /** Diagrams in the opener AND every section. */
  diagrams: DiagramSource[];
  sections: Section[];
  draft: boolean;
}

/** Where chapters live, relative to the app root. */
export const BOOK_CONTENT_DIR = "content/book";
export const CHAPTER_INDEX = "index.mdx";

export function slugFromFileName(fileName: string): string {
  return fileName.replace(/\.mdx?$/, "");
}

function readUnit(path: string, where: string) {
  const { yaml, body } = splitFrontmatter(readFileSync(path, "utf8"));
  const meta = parseFrontmatter(yaml, where);
  const headings = extractHeadings(body);
  return { meta, headings, toc: tocEntries(headings), diagrams: findDiagramFences(body).map((f) => describeDiagram(f.source)) };
}

/** Read one chapter directory: its opener and its sections. */
export function loadChapter(dir: string, slug: string): Chapter {
  const opener = readUnit(join(dir, CHAPTER_INDEX), `${slug}/${CHAPTER_INDEX}`);
  const sections: Section[] = readdirSync(dir)
    .filter((f) => /\.mdx?$/.test(f) && f !== CHAPTER_INDEX)
    .map((file) => {
      const s = slugFromFileName(file);
      const u = readUnit(join(dir, file), `${slug}/${file}`);
      return {
        chapter: slug,
        slug: s,
        title: u.meta.title,
        summary: u.meta.summary,
        order: u.meta.order,
        href: sectionHref(slug, s),
        headings: u.headings,
        toc: u.toc,
        diagrams: u.diagrams,
        draft: u.meta.draft,
      };
    })
    .filter((s) => !s.draft);
  const ordered = orderChapters(sections);
  return {
    slug,
    title: opener.meta.title,
    summary: opener.meta.summary,
    order: opener.meta.order,
    href: chapterHref(slug),
    headingCount: ordered.length,
    headings: opener.headings,
    toc: opener.toc,
    diagrams: [...opener.diagrams, ...ordered.flatMap((s) => s.diagrams)],
    sections: ordered,
    draft: opener.meta.draft,
  };
}

/** Read every chapter directory, ordered, drafts removed. */
export function loadChapters(root: string): Chapter[] {
  const base = join(root, BOOK_CONTENT_DIR);
  if (!existsSync(base)) return []; // an empty book is a valid state
  const chapters = readdirSync(base)
    .filter((d) => statSync(join(base, d)).isDirectory() && existsSync(join(base, d, CHAPTER_INDEX)))
    .map((d) => loadChapter(join(base, d), d));
  return orderChapters(chapters).filter((c) => !c.draft);
}

/** The serialisable chapter + section list the nav components share. */
export function chapterRefs(chapters: readonly Chapter[]): ChapterWithSections[] {
  return orderChapters(chapters).map((c) => ({
    slug: c.slug,
    title: c.title,
    summary: c.summary,
    order: c.order,
    href: c.href,
    headingCount: c.headingCount,
    sections: c.sections.map(({ chapter, slug, title, summary, order, href }) => ({ chapter, slug, title, summary, order, href })),
  }));
}

/** Every diagram across the book, de-duplicated by id. */
export function allDiagrams(chapters: readonly Chapter[]): DiagramSource[] {
  const byId = new Map<string, DiagramSource>();
  for (const chapter of chapters) for (const d of chapter.diagrams) byId.set(d.id, d);
  return [...byId.values()].sort((a, b) => a.id.localeCompare(b.id));
}
