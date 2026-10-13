/**
 * Fail the book build on implementation leaks in a chapter (DIG-2818 rule).
 * The rules live in lib/book/leaks.ts; this only walks content/book.
 *
 * Layout (DIG-2821, fixed DIG-3235): every chapter is a directory holding an
 * index.mdx opener plus one .mdx file per section, so the walk is
 * per-chapter, never a flat suffix filter over the top level — that filter
 * matched zero directories and reported a vacuously clean book.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const { findLeaks } = await import("../../lib/book/leaks.ts");
const DIR = process.env.BOOK_DIR ?? resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "content", "book");

/** Every .md/.mdx chapter file under a book root, as paths relative to it. */
export function collectBookFiles(root) {
  const out = [];
  for (const chapter of readdirSync(root).sort()) {
    const cdir = join(root, chapter);
    if (!statSync(cdir).isDirectory()) continue;
    for (const file of readdirSync(cdir).filter((f) => /\.mdx?$/.test(f)).sort()) out.push(join(chapter, file));
  }
  return out;
}

/** Lint every chapter file; returns the leak count (0 is clean). */
export function lintBook(root, report) {
  let total = 0;
  for (const name of collectBookFiles(root)) {
    for (const leak of findLeaks(readFileSync(join(root, name), "utf8"))) {
      total += 1;
      report(`content/book/${name}:${leak.line}  [${leak.rule}] ${leak.match}  —  ${leak.text.slice(0, 100)}`);
    }
  }
  return total;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  let total = 0;
  const errors = [];
  total = lintBook(DIR, (line) => errors.push(line));
  for (const line of errors) console.error(line);
  if (total > 0) {
    console.error(
      `\nbook lint: ${total} leak(s). digibook stays high level — move the detail into the reference docs and ` +
        "link it with <Reference>, or justify a line with {/* book-lint-allow: <reason> */}.",
    );
    process.exit(1);
  }
  console.log("book lint: clean");
}
