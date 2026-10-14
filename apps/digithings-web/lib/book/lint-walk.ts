/**
 * Which files the book lint gate reads (DIG-2884).
 *
 * The gate used to walk the book with
 * `readdirSync(DIR).filter((f) => /\.mdx?$/.test(f))`, which can only ever see
 * files sitting directly in `content/book`. A chapter is a DIRECTORY now, one
 * MDX per section, so that filter matched nothing at all: the gate opened zero
 * files and printed "book lint: clean" over every chapter in the book. That is
 * the same silent failure as the loader that started this issue - a gate that
 * cannot see the content it gates reports clean either way.
 *
 * So the walk here recurses and takes every `.md`/`.mdx` at any depth, and
 * returns paths relative to the book root with forward slashes so a caller can
 * print them and a test can compare them against what the loader serves.
 */
import { readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";

/** The file kinds the book is written in. */
const BOOK_FILE = /\.mdx?$/i;

/**
 * Every book file under `dir`, as sorted forward-slash paths relative to `dir`.
 *
 * Nothing under the book root is skipped for being in a directory: a chapter, a
 * section and a file someone dropped in the wrong place are all content, and
 * the gate is the last thing standing between them and the rendered book.
 */
export function bookContentFiles(dir: string): string[] {
  const found: string[] = [];

  const walk = (absolute: string): void => {
    const entries = readdirSync(absolute, { withFileTypes: true }).sort((a, b) =>
      a.name.localeCompare(b.name),
    );
    for (const entry of entries) {
      const child = join(absolute, entry.name);
      if (entry.isDirectory()) walk(child);
      else if (BOOK_FILE.test(entry.name)) found.push(relative(dir, child).split(sep).join("/"));
    }
  };

  walk(dir);
  return found.sort();
}