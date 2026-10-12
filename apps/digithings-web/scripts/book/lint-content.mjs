/**
 * Fail the book build on implementation leaks in a chapter (DIG-2818 rule).
 * The rules live in lib/book/leaks.ts; this only walks content/book.
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const { findLeaks } = await import("../../lib/book/leaks.ts");
const DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "content", "book");

let total = 0;
for (const name of readdirSync(DIR).filter((f) => /\.mdx?$/.test(f)).sort()) {
  for (const leak of findLeaks(readFileSync(join(DIR, name), "utf8"))) {
    total += 1;
    console.error(`content/book/${name}:${leak.line}  [${leak.rule}] ${leak.match}  —  ${leak.text.slice(0, 100)}`);
  }
}
if (total > 0) {
  console.error(
    `\nbook lint: ${total} leak(s). digibook stays high level — move the detail into the reference docs and ` +
      "link it with <Reference>, or justify a line with {/* book-lint-allow: <reason> */}.",
  );
  process.exit(1);
}
console.log("book lint: clean");
