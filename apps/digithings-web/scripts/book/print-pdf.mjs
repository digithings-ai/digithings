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
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

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
    // normalize collapses `..` before the join, so a request cannot escape the
    // export directory.
    const rel = normalize(decoded);
    let file = join(dir, rel);
    if (!file.startsWith(dir)) {
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

try {
  const page = await browser.newPage();
  // emulatedMedia "screen" on purpose: Paged.js paginates into fixed boxes and
  // its own stylesheet, and Chrome's print media would restyle on top of it.
  await page.emulateMedia({ media: "screen" });
  await page.goto(`${base}/book/print/`, { waitUntil: "networkidle" });

  // PagedBoot publishes nothing to wait on, so wait for the DOM it produces:
  // page boxes exist only after `chunk()` has run. A timeout here is a real
  // failure and exits non-zero rather than printing an unpaginated page.
  // Wait for the book's own completion marker, not for the page boxes: pagedjs
  // creates those first and the page-number pass runs after, so waiting on the
  // boxes printed a table of contents with empty references.
  await page.waitForSelector("[data-book-paginated]", { timeout: 60_000 });
  const pages = await page.locator(".pagedjs_page").count();
  if (pages < 1) throw new Error("pagination produced no pages");
  const refs = await page.$$eval("[data-book-toc-ref]", (nodes) => nodes.map((n) => n.textContent));
  const filled = refs.filter((r) => r && r.trim() !== "");
  if (refs.length && filled.length === 0) {
    throw new Error(`no table-of-contents page reference resolved (${refs.length} entries)`);
  }

  const target = process.argv[2] ?? join(APP_ROOT, "book.pdf");
  await page.pdf({
    path: target,
    format: "A4",
    printBackground: true,
    // The @page rule in the print stylesheet owns the page box, so the PDF
    // takes the geometry from the document rather than from this call.
    preferCSSPageSize: true,
  });
  console.log(`book: wrote ${target} (${pages} pages)`);
} finally {
  await browser.close();
  server.close();
}
