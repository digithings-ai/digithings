/**
 * Fail the book build on implementation leaks in a chapter (DIG-2818 rule).
 * The rules live in lib/book/leaks.ts; this only walks content/book.
 *
 * DIG-2884: the walk used to be `readdirSync(DIR).filter(f => /\.mdx?$/.test(f))`,
 * which cannot see a chapter DIRECTORY. With every chapter shaped as a
 * directory it opened zero files and printed "book lint: clean". The walk is
 * now lib/book/lint-walk.ts, shared with the tests, and a book that contains no
 * files at all is a failure rather than a pass - a gate that checked nothing
 * must never report clean.
 */
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const { findLeaks } = await import("../../lib/book/leaks.ts");
const { bookContentFiles } = await import("../../lib/book/lint-walk.ts");

/** `BOOK_LINT_DIR` is a test seam: the gate otherwise always walks its own content/book. */
const DIR = process.env.BOOK_LINT_DIR
  ? resolve(process.env.BOOK_LINT_DIR)
  : resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "content", "book");

const files = bookContentFiles(DIR);
if (files.length === 0) {
  console.error(`book lint: no .md or .mdx files under ${DIR} - the gate would pass on nothing.`);
  process.exit(1);
}

let total = 0;
for (const name of files) {
  for (const leak of findLeaks(readFileSync(join(DIR, name), "utf8"))) {
    total += 1;
    console.error(
      `content/book/${name}:${leak.line}  [${leak.rule}] ${leak.match}  —  ${leak.text.slice(0, 100)}`,
    );
  }
}
if (total > 0) {
  console.error(
    `\nbook lint: ${total} leak(s). digibook stays high level — move the detail into the reference docs and ` +
      "link it with <Reference>, or justify a line with {/* book-lint-allow: <reason> */}.",
  );
  process.exit(1);
}
console.log(`book lint: clean (${files.length} file(s))`);