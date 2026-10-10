/**
 * Render every mermaid fence in `content/book` to a static SVG (DIG-2821).
 *
 * Run by `prebuild`, so `next build` produces the same files as the print step
 * will read. It writes exactly one SVG per distinct diagram, named by the
 * content hash the pages already link to — see `lib/book/diagram.ts`, which is
 * the single source of the address.
 *
 * This is the only place a diagram is rendered. Nothing in the browser renders
 * mermaid, and nothing in the print step does either: both load the files this
 * writes, which is how "the same SVG used in the PDF" is true by construction
 * rather than by discipline.
 *
 * A real browser, not jsdom. Mermaid measures text through `SVGTextElement
 * .getBBox`, which jsdom does not implement; shimming it produces SVGs with
 * mis-sized — and visibly overlapping — labels, which is worse than no
 * diagram because it looks correct. Playwright is already this app's print
 * dependency, so the build reuses it rather than adding a second renderer.
 *
 * Fails the build on the first diagram it cannot render: a silently skipped
 * diagram ships a chapter with a hole in it and a page count that no longer
 * matches.
 */
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = dirname(fileURLToPath(import.meta.url));
const APP_ROOT = resolve(HERE, "..", "..");

// The chapter readers and the address helpers are the SAME modules the app
// uses. Node strips the type annotations and imports them directly, so the
// build step and the pages can never disagree about an id or a URL. Nothing is
// re-implemented here.
const { allDiagrams, loadChapters } = await import("../../lib/book/chapters.server.ts");

const diagrams = allDiagrams(loadChapters(APP_ROOT));
if (diagrams.length === 0) {
  console.log("book: no mermaid fences found — nothing to render");
  process.exit(0);
}

// mermaid ships a UMD bundle that defines `window.mermaid`; injecting it as a
// script tag is how the harness page below gets it without a bundler.
const MERMAID_UMD = require.resolve("mermaid/dist/mermaid.min.js");

const { chromium } = await import("playwright");

const outDir = join(APP_ROOT, "public", "book", "diagrams");
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
let written = 0;
try {
  const page = await browser.newPage();
  await page.setContent("<!doctype html><html><body></body></html>");
  await page.addScriptTag({ content: readFileSync(MERMAID_UMD, "utf8") });
  await page.evaluate(() => {
    window.mermaid.initialize({
      startOnLoad: false,
      // `base` + a short variable map, not `neutral` + a long one. Both were
      // measured here: the long neutral map made mermaid emit
      // `fill:#F` — the first character of a colour, sliced out of a value it
      // had already consumed — and every node rectangle rendered black-on-black.
      // A diagram that looks right in mermaid's preview and is a row of black
      // boxes in the book is the failure this step exists to prevent.
      //
      // `darkMode: false` is explicit: mermaid otherwise detects the page's
      // `data-theme`, and the site's default is dark.
      //
      // A static SVG cannot follow the reader's theme, so these are literals by
      // necessity. They are the light reading surface the book uses, matching
      // the ivory long-form mode /docs already defaults to.
      theme: "base",
      darkMode: false,
      // The "neo" look resolves node fills through CSS custom properties, which
      // resolve against the PAGE's theme — so a light-surface SVG rendered on the
      // site's dark theme came out with dark nodes. "classic" emits literal
      // fills and travels with the file, which is the only thing a static SVG
      // can rely on.
      look: "classic",
      flowchart: { htmlLabels: false, useMaxWidth: false },
      securityLevel: "strict",
      themeVariables: {
        background: "#FBFBF9",
        primaryColor: "#EFEBE3",
        primaryTextColor: "#16181A",
        primaryBorderColor: "#9C9891",
        lineColor: "#3F4448",
        fontFamily: "ui-monospace, monospace",
      },
    });
  });

  for (const diagram of diagrams) {
    const svg = await page.evaluate(
      ([id, source]) => window.mermaid.render(id, source).then((r) => r.svg),
      [diagram.id, diagram.source],
    );
    if (typeof svg !== "string" || !svg.includes("<svg")) {
      throw new Error(`renderer returned no svg markup for ${diagram.id}`);
    }
    // A viewBox is what lets an SVG scale. Without it the image renders at its
    // intrinsic size and the pan-and-zoom control has nothing to scale.
    const sized = /<svg[^>]*\bviewBox=/.test(svg)
      ? svg
      : svg.replace(/<svg/, '<svg viewBox="0 0 1 1" preserveAspectRatio="xMidYMid meet"');
    writeFileSync(join(APP_ROOT, "public", diagram.file), sized, "utf8");
    written += 1;
  }
} finally {
  await browser.close();
}

console.log(`book: rendered ${written} diagram(s) into public/book/diagrams`);