/**
 * The reader at `/book`, checked in a real browser under the site's real CSP.
 *
 * Two things broke on the live site with every unit test green, because both
 * only exist in a browser that enforces the production headers:
 *
 *  - every diagram was an empty frame. The recolour step served the drawings as
 *    `blob:` URLs and `img-src` does not allow `blob:`, so the browser refused
 *    each one; the HTML export then re-fetched those URLs, was refused again by
 *    `connect-src`, and wrote the file with no figures at all;
 *  - pressing PDF or HTML scrolled the contents sidebar by ~115px, because the
 *    export cells sat below the fold of one scrolling box and the click focused
 *    a button the box then scrolled into view.
 *
 * This serves the exported site (`out/`) with the CSP from
 * `lib/security-headers.mjs` — the same function that writes `public/_headers`
 * — and fails on either regression. Set BOOK_CHECK_URL to point it at a
 * deployed site instead (it then reads that site's own headers), and
 * BOOK_CHECK_SHOTS to a folder to keep screenshots of what it saw.
 *
 * Loopback only, no paid service: Playwright's Chromium, as `print-pdf.mjs`.
 */
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { digithingsCsp } from "../../lib/security-headers.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP_ROOT = resolve(HERE, "..", "..");
const OUT = join(APP_ROOT, "out");
const SHOTS = process.env.BOOK_CHECK_SHOTS ?? "";
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".png": "image/png",
  ".pdf": "application/pdf",
  ".txt": "text/plain",
};

function serve(dir) {
  const csp = digithingsCsp();
  const root = resolve(dir);
  const server = createServer((req, res) => {
    let decoded;
    try {
      decoded = decodeURIComponent((req.url ?? "/").split("?")[0]);
    } catch {
      res.writeHead(400).end("bad request");
      return;
    }
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
    res.writeHead(200, {
      "content-type": TYPES[extname(file)] ?? "application/octet-stream",
      "content-security-policy": csp,
    });
    createReadStream(file).pipe(res);
  });
  return new Promise((ok) => {
    server.listen(0, "127.0.0.1", () => ok({ server, base: `http://127.0.0.1:${server.address().port}` }));
  });
}

const failures = [];
const fail = (message) => {
  failures.push(message);
  console.error(`  ✗ ${message}`);
};
const pass = (message) => console.log(`  ✓ ${message}`);

let server;
let base = process.env.BOOK_CHECK_URL?.replace(/\/+$/, "");
if (!base) {
  if (!existsSync(join(OUT, "book", "index.html"))) {
    console.error("book: out/book/index.html does not exist — run `npm run build --workspace digithings-web` first");
    process.exit(1);
  }
  ({ server, base } = await serve(OUT));
}

const { chromium } = await import("playwright");
const browser = await chromium.launch();

async function openBook({ width, height, theme }) {
  const context = await browser.newContext({ viewport: { width, height }, acceptDownloads: true });
  await context.addInitScript((value) => {
    try {
      localStorage.setItem("dt-theme", value);
    } catch {
      // storage disabled: the page falls back to its default theme
    }
  }, theme);
  const page = await context.newPage();
  const refused = [];
  page.on("console", (message) => {
    if (message.type() === "error" && /Content Security Policy/i.test(message.text())) refused.push(message.text());
  });
  await page.goto(`${base}/book/`, { waitUntil: "load", timeout: 120_000 });
  await page.waitForSelector('.book-live[data-ready="true"]', { timeout: 120_000 });
  // The recolour runs once more after the ready marker on the cloned boxes.
  await page.waitForTimeout(1500);
  return { context, page, refused };
}

/** Every figure in the page boxes, and whether its visible drawing painted. */
function figureState(page) {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll(".book-live__stage .pagedjs_page figure[data-book-diagram]")).map((figure) => {
      const shown = Array.from(figure.querySelectorAll("img")).find((image) => getComputedStyle(image).display !== "none");
      return {
        caption: figure.querySelector("figcaption span")?.textContent ?? "",
        painted: Boolean(shown && shown.complete && shown.naturalWidth > 0),
        scheme: shown ? (shown.getAttribute("src") ?? "").split(":")[0] : "",
        src: shown?.getAttribute("src") ?? "",
      };
    }),
  );
}

async function checkFigures(theme) {
  console.log(`figures, ${theme} theme`);
  const { context, page, refused } = await openBook({ width: 1440, height: 900, theme });
  const figures = await figureState(page);
  if (figures.length === 0) fail(`${theme}: no figures in the page boxes`);
  const blank = figures.filter((figure) => !figure.painted);
  if (blank.length) fail(`${theme}: ${blank.length}/${figures.length} figures did not paint (${blank.map((f) => f.caption || f.src.slice(0, 40)).join("; ")})`);
  else pass(`${theme}: ${figures.length}/${figures.length} figures painted`);
  const notData = figures.filter((figure) => figure.scheme !== "data");
  if (notData.length) fail(`${theme}: ${notData.length} figures are not drawn in the reader's palette (src scheme ${notData[0].scheme})`);
  if (refused.length) fail(`${theme}: the CSP refused ${refused.length} loads, first: ${refused[0].slice(0, 140)}`);
  else pass(`${theme}: nothing refused by the CSP`);

  // A live theme switch redraws the figures in the new theme's colours.
  const other = theme === "light" ? "dark" : "light";
  await page.evaluate((value) => document.documentElement.setAttribute("data-theme", value), other);
  await page.waitForTimeout(1500);
  const after = await figureState(page);
  const stale = after.filter((figure, index) => !figure.painted || figure.src === figures[index]?.src);
  if (stale.length) fail(`${theme}→${other}: ${stale.length}/${after.length} figures were not redrawn`);
  else pass(`${theme}→${other}: ${after.length} figures redrawn and painted`);

  if (SHOTS) {
    await page.evaluate((value) => document.documentElement.setAttribute("data-theme", value), theme);
    await page.waitForTimeout(1200);
    const figuresOnPage = page.locator(".book-live__stage .pagedjs_page figure[data-book-diagram]");
    const count = await figuresOnPage.count();
    for (let index = 0; index < count; index += 1) {
      await figuresOnPage.nth(index).scrollIntoViewIfNeeded();
      await figuresOnPage.nth(index).screenshot({ path: join(SHOTS, `figure-${theme}-${String(index + 1).padStart(2, "0")}.png`) });
    }
  }
  await context.close();
}

/** The boxes a reader would see move, rounded to the pixel. */
function layout(page) {
  return page.evaluate(() => {
    const box = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return [rect.x, rect.y, rect.width, rect.height].map(Math.round);
    };
    return {
      nav: box(".book-nav"),
      contents: box(".book-nav > ol"),
      contentsScroll: document.querySelector(".book-nav > ol")?.scrollTop ?? 0,
      navScroll: document.querySelector(".book-nav")?.scrollTop ?? 0,
      export: box(".book-export"),
      stage: box(".book-live__stage"),
      scrollY: Math.round(window.scrollY),
      gutter: window.innerWidth - document.documentElement.clientWidth,
    };
  });
}

async function checkExport({ width, height }) {
  console.log(`export at ${width}×${height}`);
  const { context, page } = await openBook({ width, height, theme: "light" });
  for (const format of ["pdf", "html"]) {
    const before = await layout(page);
    const button = page.locator(`.book-export__btn[data-format="${format}"]`).first();
    if (!(await button.isVisible())) {
      fail(`${width}×${height}: the ${format} button is not visible`);
      continue;
    }
    const inView = await button.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return rect.top >= 0 && rect.bottom <= window.innerHeight;
    });
    if (!inView) fail(`${width}×${height}: the ${format} button is not fully on screen before the click`);
    const download = page.waitForEvent("download", { timeout: 60_000 });
    await button.click();
    const frames = [];
    for (const wait of [16, 120, 600]) {
      await page.waitForTimeout(wait);
      frames.push(await layout(page));
    }
    const saved = await download.catch(() => null);
    if (!saved) fail(`${width}×${height}: pressing ${format} saved no file`);
    const moved = frames.find((frame) => JSON.stringify(frame) !== JSON.stringify(before));
    if (moved) fail(`${width}×${height}: pressing ${format} moved the page: ${JSON.stringify(before)} → ${JSON.stringify(moved)}`);
    else pass(`${width}×${height}: pressing ${format} moved nothing`);

    if (saved && format === "html") {
      const path = await saved.path();
      const html = readFileSync(path, "utf8");
      const figures = (html.match(/data-book-diagram/g) ?? []).length;
      const drawn = (html.match(/<img [^>]*src="data:image\/svg\+xml/g) ?? []).length;
      if (figures === 0 || drawn < figures) fail(`${width}×${height}: the HTML export has ${drawn} drawings for ${figures} figures`);
      else pass(`${width}×${height}: the HTML export carries ${drawn} drawings for ${figures} figures`);
    }
  }
  await context.close();
}

try {
  await checkFigures("light");
  await checkFigures("dark");
  await checkExport({ width: 1440, height: 900 });
  await checkExport({ width: 1280, height: 720 });
  await checkExport({ width: 390, height: 844 });
} finally {
  await browser.close();
  server?.close();
}

if (failures.length) {
  console.error(`book reader: ${failures.length} failure(s)`);
  process.exit(1);
}
console.log("book reader: clean");
