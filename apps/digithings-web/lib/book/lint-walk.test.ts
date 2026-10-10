/**
 * The book lint gate has to be able to see the book (DIG-2884).
 *
 * The gate walked `content/book` with `readdirSync(DIR).filter(f => /\.mdx?$/.test(f))`.
 * A chapter is a directory now, one MDX per section, so that filter matched
 * nothing: the gate opened zero files and printed "book lint: clean" over every
 * chapter in the book. A chapter could carry a loopback host, an env var name
 * or a port and the gate would still pass - the failure mode a build gate
 * cannot have.
 *
 * So two things are pinned here. The walk descends into chapter directories and
 * reaches every file the loader serves, and the gate REFUSES when it has read
 * no files at all. The second one is what stops this bug from ever reading as
 * clean again: a silent no-op and a genuine pass look identical from outside
 * unless the gate is made to say so.
 *
 * The gate is driven as a subprocess rather than imported, because the shape
 * that failed was the shape of the whole program: zero files read, exit 0.
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";

import { bookContentFiles } from "./lint-walk";
import { BOOK_CONTENT_DIR, CHAPTER_INDEX, loadChapters } from "./chapters.server";

const ROOT = process.cwd();
const BOOK = join(ROOT, BOOK_CONTENT_DIR);
const GATE = join(ROOT, "scripts", "book", "lint-content.mjs");

const tempRoots: string[] = [];
afterAll(() => {
  for (const dir of tempRoots) rmSync(dir, { recursive: true, force: true });
});

/** A book tree on disk. `files` are paths relative to the book root. */
function makeBook(files: Record<string, string>): string {
  const dir = mkdtempSync(join(tmpdir(), "digibook-lint-"));
  tempRoots.push(dir);
  for (const [rel, body] of Object.entries(files)) {
    const abs = join(dir, rel);
    mkdirSync(dirname(abs), { recursive: true });
    writeFileSync(abs, body);
  }
  return dir;
}

interface GateRun {
  status: number;
  output: string;
}

/** Run the real gate over `bookDir`. The env seam keeps the test off the shipped book. */
function runGate(bookDir: string): GateRun {
  const run = spawnSync(process.execPath, [GATE], {
    cwd: ROOT,
    encoding: "utf8",
    env: { ...process.env, BOOK_LINT_DIR: bookDir },
  });
  return { status: run.status ?? -1, output: `${run.stdout ?? ""}${run.stderr ?? ""}` };
}

/**
 * One line that trips every leak rule at once. If any rule stops firing, the
 * gate assertions below become green for the wrong reason, so this is asserted
 * directly rather than assumed.
 */
const LEAKY = "Set DIGIKEY_JWKS_URL before you open http://localhost/ and call digigraph :8000 with api_key.\n";

describe("the book walk", () => {
  it("descends into chapter directories", () => {
    const book = makeBook({
      "01-alpha/index.mdx": "---\ntitle: A\norder: 1\nsummary: s\n---\n",
      "01-alpha/01-first.mdx": "---\ntitle: First\norder: 1\nsummary: s\n---\n",
      "01-alpha/02-second.mdx": "---\ntitle: Second\norder: 2\nsummary: s\n---\n",
      "loose.mdx": "A file that sits at the book root.\n",
      "notes/readme.md": "Not a chapter, still book content.\n",
    });

    // The filter this replaces could not produce any of the directory paths.
    expect(bookContentFiles(book)).toEqual([
      "01-alpha/01-first.mdx",
      "01-alpha/02-second.mdx",
      "01-alpha/index.mdx",
      "loose.mdx",
      "notes/readme.md",
    ]);
  });

  it("reaches every file the loader serves", () => {
    const files = bookContentFiles(BOOK);
    expect(files.length).toBeGreaterThan(0);

    const chapters = loadChapters(ROOT);
    expect(chapters.length).toBeGreaterThan(0);

    // The invariant that broke: the loader serves these, so the gate must read
    // them. A chapter that vanishes from the gate is a chapter nobody checks.
    const served = chapters.flatMap((chapter) => [
      `${chapter.slug}/${CHAPTER_INDEX}`,
      ...chapter.sections.map((section) => `${chapter.slug}/${section.slug}.mdx`),
    ]);
    expect(served.length).toBeGreaterThan(0);
    for (const path of served) expect(files).toContain(path);

    // And nothing in the walk points at a file that is not there.
    for (const path of files) expect(existsSync(join(BOOK, path))).toBe(true);
  });
});

describe("the gate", () => {
  it("catches a leak inside a chapter directory", () => {
    const book = makeBook({
      "01-alpha/index.mdx": "---\ntitle: A\norder: 1\nsummary: s\n---\n",
      "01-alpha/01-leaky.mdx": LEAKY,
    });

    const run = runGate(book);
    expect(run.status).toBe(1);
    // The path in the message is what proves the directory was opened: the old
    // walker reported nothing here and exited 0.
    expect(run.output).toContain("01-alpha/01-leaky.mdx");
    expect(run.output).toContain("env-name");
    expect(run.output).toContain("loopback");
    expect(run.output).toContain("port");
    expect(run.output).toContain("secret-word");
  });

  it("passes a clean book", () => {
    const book = makeBook({
      "01-alpha/index.mdx": "---\ntitle: A\norder: 1\nsummary: s\n---\n",
      "01-alpha/01-first.mdx": "---\ntitle: First\norder: 1\nsummary: s\n---\nA chapter page.\n",
    });

    const run = runGate(book);
    expect(run.status).toBe(0);
    expect(run.output).toContain("book lint: clean");
  });

  it("refuses a book it read nothing from", () => {
    // The shape the bug took: the walk matches no file and the gate still says
    // clean. Zero files is a failure, not a pass.
    const run = runGate(makeBook({ "notes/readme.txt": "no book files here\n" }));
    expect(run.status).toBe(1);
    expect(run.output).not.toContain("book lint: clean");
    expect(run.output).toContain("no .md or .mdx files");
  });
});