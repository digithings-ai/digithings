/**
 * Print the book to a PDF with Playwright (DIG-2821).
 *
 * Runs against the EXPORTED site (`out/`), not a dev server: the artifact is
 * the thing that ships, so it is the thing that is printed. Nothing about the
 * operator's browser — paper size, margins, headers and footers, "fit to
 * page", a saved print dialog — can reach the result.
 *
 * The static server below exists because `output: "export"` emits absolute
 * `/book/…` paths, which do not resolve over `file://`. It is a fixture, not
 * a product surface, and it binds to loopback only.
 */
import { copyFileSync, createReadStream, existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP_ROOT = resolve(HERE, "..", "..");
const OUT = join(APP_ROOT, "out");
const TARGET = join(OUT, "book", "print", "index.html");

if (!existsSync(TARGET)) {
  console.error(`book: ${TARGET} does not exist — run \`npm run build --workspace digithings-web\` first`);
  process.exit(1);
}

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".png": "image/png",
};

/** A read-only static server over `out/`. Returns its base URL. */
function serve(dir) {
  const server = createServer((req, res) => {
    // A malformed percent-escape is a bad request, not a crash: the export is
    // full of RSC prefetch URLs and one of them throws `URIError: URI
    // malformed`, which killed the run before the PDF was written.
    let decoded;
    try {
      decoded = decodeURIComponent((req.url ?? "/").split("?")[0]);
    } catch {
      res.writeHead(400).end("bad request");
      return;
    }
    // `startsWith(dir)` treats `out-evil` as inside `out`. Resolve against the
    // export root and refuse any relative path that still contains `..`.
    const root = resolve(dir);
    let file = resolve(root, decoded.replace(/^\/+/, ""));
    if (relative(root, file).split(sep).includes("..")) {
      res.writeHead(403).end("forbidden");
      return;
    }
    if (existsSync(file) && statSync(file).isDirectory()) file = join(file, "index.html");
    if (!existsSync(file)) {
      res.writeHead(404).end("not found");
      return;
    }
    res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
    createReadStream(file).pipe(res);
  });
  return new Promise((ok) => {
    server.listen(0, "127.0.0.1", () => ok({ server, base: `http://127.0.0.1:${server.address().port}` }));
  });
}

const { server, base } = await serve(OUT);
const { chromium } = await import("playwright");
const browser = await chromium.launch();

/**
 * The palettes that get a printed edition, so their download is a file rather
 * than a twenty-second render in the browser. The default entry is the site's
 * own theme (dark, accent = ink). Adding a palette here costs a few seconds of
 * build time and one file; a palette that is not here still works, it is just
 * built in the browser.
 */
/**
 * The palettes that get a printed edition, in both themes. A download for one
 * of these is a file fetch (tens of milliseconds); anything else is rendered in
 * the browser (~20s) and says so while it works.
 *
 * Ten files at 2.4MB each: the point is that the common themes never wait, and
 * the list is cheap to extend — add a palette and one line appears in each
 * theme.
 */
/**
 * One edition. `/book` is a light, still page, and the print is a fixed
 * artefact of it, so there is nothing per-theme to print. A palette change does
 * not alter the download.
 */
const PRINTED = [{ theme: "light", palette: "", file: "the-digithings-book.pdf" }];
const THEMES = ["light"];

/**
 * One edition: paginate the print route in the given theme and screenshot every
 * finished page box into a PDF.
 *
 * The theme is set before the document loads. The site's own tokens do the rest
 * — background, ink, accent, the pixel field's hue — so a dark edition is drawn
 * dark rather than printed light and inverted. `seed` is shared by both
 * editions, so the field on the cover is the same pattern in each, differing
 * only in colour.
 */
async function openBook(seed, theme) {
  const page = await browser.newPage({ deviceScaleFactor: 1.75 });
  await page.addInitScript((value) => {
    try {
      localStorage.setItem("dt-theme", value);
    } catch {
      /* a blocked storage still gets the attribute below */
    }
    document.documentElement.setAttribute("data-theme", value);
  }, theme);
  // emulatedMedia "screen" on purpose: Paged.js paginates into fixed boxes and
  // its own stylesheet, and Chrome's print media would restyle on top of it.
  await page.emulateMedia({ media: "screen" });
  await page.goto(`${base}/book/print/?seed=${seed}`, { waitUntil: "networkidle" });

  // Wait for the book's own completion marker, not for the page boxes: pagedjs
  // creates those first and the page-number pass runs after, so waiting on the
  // boxes printed a table of contents with empty references. The source
  // document is hidden after pagination, so wait for the marker to be
  // attached, not visible.
  await page.waitForSelector("[data-book-paginated]", { state: "attached", timeout: 60_000 });
  const pages = await page.locator(".pagedjs_page").count();
  if (pages < 1) throw new Error(`pagination produced no pages (${theme})`);
  const refs = await page.$$eval("[data-book-toc-ref]", (nodes) => nodes.map((n) => n.textContent));
  const filled = refs.filter((r) => r && r.trim() !== "");
  if (refs.length && filled.length === 0) {
    throw new Error(`no table-of-contents page reference resolved (${theme}, ${refs.length} entries)`);
  }

  // `/book` labels its contents from this map. The images beside it come from
  // the PDF (scripts/book/page-images.mjs), so both are taken from the same
  // pagination and a page number cannot name a different page than the
  // download.
  const map = await page.$$eval(".pagedjs_page [data-book-anchor]", (nodes) => {
    const out = {};
    for (const node of nodes) {
      const slug = node.getAttribute("data-book-anchor");
      const page = node.closest(".pagedjs_page")?.dataset.bookPage;
      if (slug && page && !(slug in out)) out[slug] = Number(page);
    }
    return out;
  });

  return { page, pages, map };
}

/**
 * Screenshot every page box of the open book into one PDF.
 *
 * The book is paginated once and captured once per palette: switching the
 * palette attribute recolours the same page boxes, so five editions cost one
 * pagination and five capture passes rather than five of each.
 */
async function captureEdition(page, pages, entry) {
  // Palette only: the theme is set before the document loads, because the
  // diagrams choose their light or dark file by attribute and a late switch
  // left a light page carrying a drawing coloured for the dark one.
  await page.evaluate((palette) => {
    if (palette) document.documentElement.setAttribute("data-palette", palette);
    else document.documentElement.removeAttribute("data-palette");
  }, entry.palette);
  await page.waitForTimeout(400);
  const file = entry.file;
  const target = join(APP_ROOT, "public", "book", file);
  mkdirSync(dirname(target), { recursive: true });

  // Print the page boxes we already have, one image per sheet. Chrome's own
  // pagination re-flowed the fixed boxes: it packed short pages together,
  // pushed chapter openers to the foot of a sheet, and inserted blank pages.
  // A screenshot of each finished page box is the only faithful copy of what
  // Paged.js laid out.
  const { PDFDocument } = await import("pdf-lib");
  const A4 = { width: 595.28, height: 841.89 };
  const pdf = await PDFDocument.create();
  pdf.setTitle("The digithings book");
  pdf.setAuthor("digithings");
  pdf.setSubject("Self-hosted AI infrastructure: why it matters, how it scales, and what it costs.");
  pdf.setCreator("digithings.ai/book");
  for (let i = 0; i < pages; i += 1) {
    const shot = await page.locator(".pagedjs_page").nth(i).screenshot();
    const jpeg = await sharp(shot).jpeg({ quality: 66 }).toBuffer();
    const image = await pdf.embedJpg(jpeg);
    const sheet = pdf.addPage([A4.width, A4.height]);
    // Full bleed: the page box already carries the theme's background and its
    // own @page margins. Drawing it inset produced a visible frame around a
    // differently coloured page.
    sheet.drawImage(image, { x: 0, y: 0, ...A4 });
  }
  await (await import("node:fs/promises")).writeFile(target, await pdf.save());
  return { pages, theme: entry.theme, palette: entry.palette, file };
}

try {
  // One seed for the whole run: every palette gets the same field pattern, so
  // the editions differ only in colour. A new build picks a new one.
  const seed = Math.floor(Math.random() * 100_000);
  const written = [];
  let pages = 0;
  let map = {};
  for (const theme of ["dark", "light"]) {
    const entries = PRINTED.filter((entry) => entry.theme === theme);
    if (!entries.length) continue;
    const book = await openBook(seed, theme);
    pages = book.pages;
    map = book.map;
    for (const entry of entries) {
      written.push(await captureEdition(book.page, book.pages, entry));
    }
    await book.page.close();
  }

  mkdirSync(join(APP_ROOT, "lib", "book", "generated"), { recursive: true });
  writeFileSync(
    join(APP_ROOT, "lib", "book", "generated", "pages.json"),
    `${JSON.stringify(
      {
        pages,
        map,
        seed,
        editions: PRINTED.map((entry) => ({
          palette: entry.palette,
          theme: entry.theme,
          file: entry.file,
        })),
      },
      null,
      2,
    )}\n`,
  );

  // The exported site is what ships; keep every download in it without
  // requiring a second build after printing.
  for (const entry of PRINTED) {
    const exported = join(OUT, "book", entry.file);
    mkdirSync(dirname(exported), { recursive: true });
    copyFileSync(join(APP_ROOT, "public", "book", entry.file), exported);
  }
  console.log(
    `book: wrote ${pages} page(s) in ${written.length} edition(s), seed ${seed}`,
  );
} finally {
  await browser.close();
  server.close();
}
