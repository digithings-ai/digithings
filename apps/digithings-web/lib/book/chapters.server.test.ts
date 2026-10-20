/**
 * The book toolchain contract (DIG-2884).
 *
 * Three properties, each of which a chapter author is told to rely on and each
 * of which used to fail silently:
 *
 *   1. `content/book/<chapter>/` is a DIRECTORY, one MDX per section. A loader
 *      that only looked at files dropped the whole chapter with no error, so a
 *      missing chapter read as an unpublished one.
 *   2. Every section is its own page at `/book/<chapter>/<section>/`. The route
 *      has to carry two path segments or the URL the nav hands out 404s.
 *   3. `Reference` exists and is registered in the MDX component map, because
 *      editorial rule 1 (implementation detail lives in Reference cards) is
 *      otherwise unsatisfiable from a chapter.
 *
 * Nothing else in `lib/book` touches the filesystem, so the loader was
 * untested: a regression here is invisible until a chapter silently vanishes.
 */

import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";

import Reference, { REPO_BLOB, resolveReferenceHref } from "@/components/book/Reference";
import {
  BOOK_CONTENT_DIR,
  CHAPTER_INDEX,
  chapterRefs,
  loadChapters,
  slugFromFileName,
} from "./chapters.server";
import { chapterHref, sectionHref } from "./toc";

/** The app root, so the shipped book can be read through the same code. */
const ROOT = process.cwd();
const BOOK = join(ROOT, BOOK_CONTENT_DIR);
const ROUTES = join(ROOT, "app", "book");

/** A unit file. `order` is the book's spine, never the file name. */
function unit(title: string, order: number, summary: string, body = "Words.", extra = ""): string {
  return `---\ntitle: ${title}\norder: ${order}\nsummary: ${summary}\n${extra}---\n\n${body}\n`;
}

const tempRoots: string[] = [];

/** A throwaway book root holding a chapter DIRECTORY per chapter. */
function makeBook(files: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), "digibook-"));
  tempRoots.push(root);
  for (const [rel, contents] of Object.entries(files)) {
    const abs = join(root, BOOK_CONTENT_DIR, rel);
    mkdirSync(join(abs, ".."), { recursive: true });
    writeFileSync(abs, contents);
  }
  return root;
}

afterAll(() => {
  for (const root of tempRoots) rmSync(root, { recursive: true, force: true });
});

describe("loadChapters reads a chapter directory", () => {
  // Two chapter directories, named so that alphabetical order is the REVERSE of
  // frontmatter order: `aa-beta` sorts first by name but comes second by `order`.
  const root = makeBook({
    "zz-alpha/index.mdx": unit("Alpha", 2, "The second chapter."),
    "zz-alpha/01-first.mdx": unit("First", 1, "The first section."),
    "zz-alpha/02-second.mdx": unit("Second", 2, "The second section."),
    "zz-alpha/99-unpublished.mdx": unit("Unpublished", 99, "Not for readers.", "Words.", "draft: true\n"),
    "aa-beta/index.mdx": unit("Beta", 1, "The first chapter."),
    "aa-beta/01-only.mdx": unit("Only", 1, "The only section."),
    // Neither of these is a chapter. A flat loader takes the first as one.
    "loose.mdx": unit("Loose", 5, "A file at the book root."),
    "99-noindex/README.md": "No opener, so no chapter.\n",
  });

  it("descends into chapter directories instead of dropping them", () => {
    const chapters = loadChapters(root);
    // A flat `readdirSync` filter over `.mdx?` finds `loose.mdx` and nothing
    // else, so this assertion is the one that fails if the loader regresses.
    expect(chapters.map((c) => c.slug)).toEqual(["aa-beta", "zz-alpha"]);
  });

  it("orders chapters by frontmatter, not by directory name", () => {
    const chapters = loadChapters(root);
    expect(chapters.map((c) => c.title)).toEqual(["Beta", "Alpha"]);
    expect(chapters.map((c) => c.order)).toEqual([1, 2]);
  });

  it("reads the opener as the chapter and the sibling files as its sections", () => {
    const [beta, alpha] = loadChapters(root);
    expect(beta.summary).toBe("The first chapter.");
    expect(beta.headingCount).toBe(1);
    expect(alpha.sections.map((s) => s.slug)).toEqual(["01-first", "02-second"]);
    expect(alpha.sections.map((s) => s.title)).toEqual(["First", "Second"]);
  });

  it("skips a draft section without skipping the chapter", () => {
    const alpha = loadChapters(root)[1];
    expect(alpha.sections.map((s) => s.slug)).not.toContain("99-unpublished");
    // A section that is only there as a draft must not hide the other three.
    expect(alpha.sections).toHaveLength(2);
  });

  it("ignores a book-root MDX file and a directory with no opener", () => {
    const slugs = loadChapters(root).map((c) => c.slug);
    expect(slugs).not.toContain("loose");
    expect(slugs).not.toContain("99-noindex");
  });

  it("returns an empty book, not an error, when there is no content at all", () => {
    expect(loadChapters(makeBook({}))).toEqual([]);
  });

  it("refuses a section with no summary rather than publishing a blank one", () => {
    const broken = makeBook({
      "01-a/index.mdx": unit("A", 1, "Summary."),
      "01-a/01-b.mdx": "---\ntitle: B\norder: 1\n---\n\nWords.\n",
    });
    // The alternative is a live page with an empty summary, which is the same
    // class of silent failure this suite exists to stop.
    expect(() => loadChapters(broken)).toThrow(/summary/);
  });
});

describe("every section gets its own two-segment URL", () => {
  const root = makeBook({
    "01-alpha/index.mdx": unit("Alpha", 1, "Chapter summary."),
    "01-alpha/01-first.mdx": unit("First", 1, "First section."),
    "01-alpha/02-second.mdx": unit("Second", 2, "Second section."),
  });

  it("builds /book/<chapter>/<section>/ and /book/<chapter>/", () => {
    expect(sectionHref("01-alpha", "01-first")).toBe("/book/01-alpha/01-first/");
    expect(chapterHref("01-alpha")).toBe("/book/01-alpha/");
    expect(sectionHref("01-alpha", "01-first").split("/").filter(Boolean)).toHaveLength(3);
    expect(chapterHref("01-alpha").split("/").filter(Boolean)).toHaveLength(2);
  });

  it("hands every section a URL whose file exists on disk", () => {
    const refs = chapterRefs(loadChapters(root));
    const hrefs = refs.flatMap((c) => c.sections.map((s) => s.href));
    expect(hrefs).toEqual(["/book/01-alpha/01-first/", "/book/01-alpha/02-second/"]);
    for (const chapter of refs) {
      for (const section of chapter.sections) {
        // `/book/<chapter>/<section>/` is the route; `content/book/<chapter>/<section>.mdx`
        // is what that route imports. The two must name the same file, so the URL
        // path is resolved against this fixture's own book directory, not the
        // shipped one: the `/book/` prefix becomes `content/book/`.
        const fromHref = join(
          root,
          BOOK_CONTENT_DIR,
          `${section.href.replace(/^\/book\//, "").replace(/\/$/, "")}.mdx`,
        );
        expect(existsSync(fromHref)).toBe(true);
        expect(fromHref).toBe(join(root, BOOK_CONTENT_DIR, chapter.slug, `${section.slug}.mdx`));
      }
    }
  });

  it("routes sections at [chapter]/[section], two dynamic segments", () => {
    // The directory name IS the route: a one-segment page cannot match
    // /book/<chapter>/<section>/ however the loader names the section.
    expect(existsSync(join(ROUTES, "[chapter]", "[section]", "page.tsx"))).toBe(true);
    // Control: the assertion above is a real path check, not a constant.
    expect(existsSync(join(ROUTES, "[chapter]", "[section]", "[section]", "page.tsx"))).toBe(false);
  });

  it("turns a file name into a slug with no extension", () => {
    expect(slugFromFileName("01-first.mdx")).toBe("01-first");
    expect(slugFromFileName("01-first.md")).toBe("01-first");
  });
});

describe("the shipped book satisfies the contract", () => {
  it("is readable through the loader from the app root", () => {
    // Guards the cwd assumption the rest of this describe block relies on.
    expect(existsSync(BOOK)).toBe(true);
    expect(loadChapters(ROOT).length).toBeGreaterThan(0);
  });

  it("gives every shipped section a URL backed by a file", () => {
    const sections = chapterRefs(loadChapters(ROOT)).flatMap((c) =>
      c.sections.map((s) => ({ book: c.slug, ...s })),
    );
    expect(sections.length).toBeGreaterThan(0);
    for (const s of sections) {
      expect(s.href).toBe(sectionHref(s.book, s.slug));
      expect(existsSync(join(BOOK, s.book, `${s.slug}.mdx`))).toBe(true);
    }
  });

  it("ships one opener per chapter directory and no loose chapter files", () => {
    const chapters = loadChapters(ROOT);
    expect(chapters.every((c) => c.sections.length > 0)).toBe(true);
    for (const c of chapters) expect(existsSync(join(BOOK, c.slug, CHAPTER_INDEX))).toBe(true);
  });
});

describe("Reference: the card editorial rule 1 requires", () => {
  it("points a repo: link at the file in the repository", () => {
    expect(resolveReferenceHref("repo:docs/SELF_HOST.md")).toBe(`${REPO_BLOB}/docs/SELF_HOST.md`);
    expect(resolveReferenceHref("repo:/docs/x.md")).toBe(`${REPO_BLOB}/docs/x.md`);
  });

  it("leaves an ordinary link alone", () => {
    expect(resolveReferenceHref("/docs/api")).toBe("/docs/api");
    expect(resolveReferenceHref("https://example.test/a")).toBe("https://example.test/a");
  });

  it("renders the kind, the title and the body the author wrote", async () => {
    const { renderToStaticMarkup } = await import("react-dom/server");
    const html = renderToStaticMarkup(
      Reference({ href: "repo:docs/toc.md", title: "Table of contents", kind: "guide", children: "Every section, in order." }),
    );
    expect(html).toContain(`href="${REPO_BLOB}/docs/toc.md"`);
    expect(html).toContain("go deeper · guide");
    expect(html).toContain("Table of contents");
    expect(html).toContain("Every section, in order.");
    // Children go in a div, because MDX wraps them in <p> and <p> inside <span>
    // is rewritten by the HTML parser before React hydrates.
    expect(html).toContain("<div");
  });

  it("is registered in the MDX component map, so a chapter can use it", () => {
    const source = readFileSync(join(ROOT, "mdx-components.tsx"), "utf8");
    expect(source).toMatch(/import Reference from "@\/components\/book\/Reference"/);
    // Both halves: the import proves the module resolves, the bare key proves the
    // card is reachable from MDX.
    expect(source).toMatch(/^\s{4}Reference,$/m);
  });
});
