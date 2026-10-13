/**
 * The lint walker must see per-section chapter files (DIG-3235).
 *
 * The old walker filtered the top-level `content/book` listing on an .mdx
 * suffix, which matches zero chapter directories — so it always reported
 * clean without opening a single file. These tests pin the walk, not the
 * rules (the rules are pinned in lib/book/leaks.test.ts).
 */
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { collectBookFiles, lintBook } from "./lint-content.mjs";

const BOOK_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "content", "book");

function fixture(): string {
  const root = mkdtempSync(join(tmpdir(), "book-lint-"));
  const chapter = join(root, "01-example");
  mkdirSync(chapter, { recursive: true });
  writeFileSync(
    join(chapter, "index.mdx"),
    "---\ntitle: Example\norder: 1\nsummary: An opener.\n---\n\nNothing leaky here.\n",
  );
  writeFileSync(join(chapter, "01-clean.mdx"), "---\ntitle: Clean\norder: 1\nsummary: Clean.\n---\n\nPlain prose.\n");
  writeFileSync(
    join(chapter, "02-leaky.mdx"),
    "---\ntitle: Leaky\norder: 2\nsummary: Leaky.\n---\n\nPoint it at localhost for now.\n",
  );
  return root;
}

describe("collectBookFiles", () => {
  it("sees the real book's per-section files, not zero", () => {
    const files = collectBookFiles(BOOK_ROOT);
    expect(files.length).toBeGreaterThan(0);
    expect(files).toContain(join("01-why-a-book", "index.mdx"));
    expect(files).toContain(join("02-how-the-book-is-built", "02-the-one-address-rule.mdx"));
  });

  it("ignores stray top-level files", () => {
    const files = collectBookFiles(fixture());
    expect(files).toContain(join("01-example", "02-leaky.mdx"));
    expect(files.every((f) => f.startsWith(`01-example${"/"}`))).toBe(true);
  });
});

describe("lintBook", () => {
  it("reports the leaky section with its chapter path", () => {
    const lines: string[] = [];
    const total = lintBook(fixture(), (line: string) => lines.push(line));
    expect(total).toBe(1);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toContain(join("01-example", "02-leaky.mdx"));
    expect(lines[0]).toContain("[loopback]");
  });
});
