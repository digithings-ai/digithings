/**
 * Rasterise the printed book into the page images `/book` scrolls through.
 *
 * The web page shows the PDF's own pages rather than re-paginating in the
 * browser: a live pagedjs pass reflowed with the viewport (19 pages at 1280px,
 * 20 at 1440), so the contents' page numbers stopped matching the download.
 * The PDF is the fixed artefact, so its pages are what the reader sees.
 *
 * Run after `npm run book:pdf`, which regenerates both the PDF and the map in
 * `lib/book/generated/pages.json`:
 *
 *   npm run book:pdf && npm run book:pages
 *
 * Needs `pdftoppm` (poppler) on PATH. The output is committed, so a contributor
 * who is only reading or editing prose never needs this.
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import sharp from "sharp";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP_ROOT = resolve(HERE, "..", "..");
const EDITIONS = [
  { pdf: "the-digithings-book.pdf", out: join(APP_ROOT, "public", "book", "pages") },
  { pdf: "the-digithings-book-dark.pdf", out: join(APP_ROOT, "public", "book", "pages", "dark") },
];
const TMP = join(APP_ROOT, ".book-pages-tmp");
/** Half the printed 150dpi width: crisp on a 2x screen, ~140KB a page. */
const WIDTH = 1240;

try {
  for (const edition of EDITIONS) {
    const pdf = join(APP_ROOT, "public", "book", edition.pdf);
    rmSync(TMP, { recursive: true, force: true });
    mkdirSync(TMP, { recursive: true });
    mkdirSync(edition.out, { recursive: true });

    execFileSync("pdftoppm", ["-r", "150", "-png", pdf, join(TMP, "page")], {
      stdio: "inherit",
    });

    const sources = readdirSync(TMP)
      .filter((file) => file.endsWith(".png"))
      .sort();
    if (sources.length === 0) throw new Error(`pdftoppm produced no pages for ${edition.pdf}`);

    let bytes = 0;
    for (const [index, file] of sources.entries()) {
      const target = join(edition.out, `${String(index + 1).padStart(2, "0")}.webp`);
      await sharp(join(TMP, file)).resize({ width: WIDTH }).webp({ quality: 78 }).toFile(target);
      bytes += statSync(target).size;
    }
    console.log(
      `pages: ${sources.length} webp page(s) from ${edition.pdf}, ${(bytes / 1_048_576).toFixed(2)} MB`,
    );
  }
  rmSync(TMP, { recursive: true, force: true });
} catch (error) {
  rmSync(TMP, { recursive: true, force: true });
  if (String(error).includes("ENOENT")) {
    console.error("pages: pdftoppm not found — install poppler (`brew install poppler`)");
  }
  throw error;
}
