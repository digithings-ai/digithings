#!/usr/bin/env node
/**
 * book:lint - the digibook editorial gate (rule 1).
 *
 * The book is a high-level architectural description. It must not carry the
 * detail that belongs in the reference material, so this fails the build on the
 * shapes that detail always takes: environment variable names, addresses, port
 * suffixes, file paths and secret-like vocabulary.
 *
 * Scoped to the book content directory. It does not check the repository: most
 * of the repository is implementation, which is exactly what the book is not.
 *
 * SELF-EXCLUSION: every pattern below is written as a literal, so this file
 * contains every shape it forbids. Counting it would make the gate permanently
 * red and therefore useless as evidence, so the gate source is excluded by
 * name. The exclusion is a named constant so that widening it is a visible edit.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

/** This file. See the note above: it must not scan itself. */
export const GATE_SOURCE = "scripts/book-lint.mjs";

/** Book content root, relative to the app directory. */
export const BOOK_DIR = "content/book";

/**
 * Each rule is `[id, pattern, what it forbids]`. Patterns are written against
 * the markdown/MDX prose, so they are deliberately narrow: a rule that fires on
 * ordinary English gets switched off by its first false positive, which is the
 * same failure as a gate nobody reads.
 */
export const RULES = [
  ["env-name", /\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g, "environment variable name"],
  ["localhost", /\b(?:localhost|127\.0\.0\.1)\b/g, "local address"],
  ["port", /:\d{2,5}\b/g, "port suffix"],
  ["secret-word", /\b(?:secrets?|passwords?|passphrases?|api[ _-]?keys?|credentials?|private[ _-]?keys?|bearers?|tokens?)\b/gi, "secret-like vocabulary"],
  ["file-path", /\b[\w.-]+\/[\w.-]+\.(?:md|mdx|ts|tsx|js|jsx|py|json|ya?ml|toml|sql)\b/g, "file path"],
  ["call-signature", /\b\w+\([^)]*\)\s*(?:->|:)/g, "function signature"],
];

/** Skip the gate source and anything a dotfile rule excludes. */
function isExcluded(name) {
  return relative(name, GATE_SOURCE) === "" || name.includes("node_modules");
}

/** Every text file under `dir`, recursively, excluding the gate source. */
export function bookFiles(dir) {
  const out = [];
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = join(dir, entry);
    if (isExcluded(full)) continue;
    if (statSync(full).isDirectory()) out.push(...bookFiles(full));
    else if (/\.mdx?$/.test(entry)) out.push(full);
  }
  return out;
}

/** Every finding in one file, as `{ id, what, line, text }`. */
export function lintFile(path, source) {
  const findings = [];
  source.split("\n").forEach((line, i) => {
    // Fenced code holds diagrams and labels, not prose, but the gate is
    // deliberately applied to the whole file: a diagram label is still book
    // text and must obey the same rules.
    for (const [id, pattern, what] of RULES) {
      const re = new RegExp(pattern.source, pattern.flags);
      const hit = re.exec(line);
      if (hit) findings.push({ id, what, line: i + 1, text: line.trim().slice(0, 90) });
    }
  });
  return findings;
}

/**
 * The app directory, derived from this file's own location and NOT from the
 * process working directory. Resolving the book against the caller's cwd is a
 * trap: run the gate from the repository root and it finds no content, reports
 * zero files and prints OK, which reads exactly like a chapter that passes.
 */
export const APP_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");

function main() {
  const root = join(APP_DIR, BOOK_DIR);
  const files = bookFiles(root);
  if (files.length === 0) {
    // A green line having scanned nothing is not evidence. Say so and fail.
    console.error(`book:lint: no chapter files under ${relative(process.cwd(), root) || BOOK_DIR} - refusing to report OK`);
    process.exitCode = 1;
    return;
  }
  let total = 0;
  for (const file of files) {
    const findings = lintFile(file, readFileSync(file, "utf8"));
    for (const f of findings) {
      total++;
      console.log(`  ${f.what} (${f.id}) ${relative(root, file)}:${f.line}  ${f.text}`);
    }
  }
  if (total > 0) {
    console.log(`book:lint: ${total} finding(s) in ${files.length} chapter file(s). The book carries no implementation detail.`);
    process.exitCode = 1;
    return;
  }
  console.log(`book:lint: OK (${files.length} chapter file(s) scanned)`);
}

if (process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop())) main();
