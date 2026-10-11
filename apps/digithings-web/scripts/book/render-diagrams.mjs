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

// ---------------------------------------------------------------------------
// Theme: one SVG per colour scheme, both from packages/design/tokens.css.
//
// An SVG loaded through <img> cannot read the page's CSS custom properties, so
// "follow the theme" means rendering the diagram once per theme with that
// theme's token values baked in, and letting the page show the matching file.
// The values are READ from tokens.css, not copied, so a palette change reaches
// the diagrams on the next build. The light file is the one the PDF prints.
// ---------------------------------------------------------------------------
const TOKENS_CSS = readFileSync(resolve(APP_ROOT, "..", "..", "packages", "design", "tokens.css"), "utf8");

function themeTokens(theme) {
  const block = new RegExp(`:root\\[data-theme="${theme}"\\]\\s*\\{([\\s\\S]*?)\\n\\}`).exec(TOKENS_CSS);
  if (!block) throw new Error(`tokens.css has no :root[data-theme="${theme}"] block`);
  const out = {};
  for (const name of ["bg", "surface", "surface-2", "ink", "ink-soft", "accent"]) {
    const m = new RegExp(`--${name}:\\s*(#[0-9A-Fa-f]{6})`).exec(block[1]);
    if (!m) throw new Error(`tokens.css ${theme} block has no hex --${name}`);
    out[name] = m[1];
  }
  return out;
}

const FONT_FAMILY = '"Geist Mono", ui-monospace, monospace';
// Geist Mono is embedded in every SVG as a data: URI. An <img>-loaded SVG may
// not fetch external fonts, so without this the browser falls back to whatever
// monospace it has, whose metrics differ from the ones mermaid measured with —
// labels then overflow their boxes. Embedding makes measure == display.
// `geist` does not export its font files, so resolve the package root.
const GEIST_MONO = join(dirname(dirname(require.resolve("geist/font/mono"))), "dist", "fonts", "geist-mono", "GeistMono-Regular.woff2");
const FONT_B64 = readFileSync(GEIST_MONO).toString("base64");
const FONT_FACE = `@font-face{font-family:"Geist Mono";src:url(data:font/woff2;base64,${FONT_B64}) format("woff2");font-weight:100 900;font-style:normal;}`;

// The digibook mermaid theme: the terminal look of the UI kit. Sharp corners,
// hairline rules, monospace labels, the kit's accent for the things a reader
// follows (edges' heads, cluster titles), everything else in ink. Applied to
// EVERY diagram through the one init call below, so a chapter cannot opt out,
// and the same files feed the web page and the PDF.
function terminalThemeCss(t) {
  return [
    "rect,polygon,.node path,.cluster rect,.actor,.note,.labelBox{rx:0 !important;ry:0 !important;stroke-width:1px !important}",
    `.cluster rect{fill:${t["surface-2"]} !important;stroke:${t["ink-soft"]} !important;stroke-dasharray:3 3}`,
    `.cluster-label text,.cluster-label tspan{fill:${t.accent} !important;letter-spacing:.04em;text-transform:lowercase}`,
    ".flowchart-link,.messageLine0,.messageLine1,.relation{stroke-width:1px !important}",
    `marker path,.arrowheadPath,.arrowMarkerPath{fill:${t.accent} !important;stroke:${t.accent} !important}`,
    `.edgeLabel rect,.labelBkg{fill:${t.bg} !important;opacity:1}`,
    `.edgeLabel text,.edgeLabel tspan{fill:${t["ink-soft"]} !important}`,
    // Sequence diagrams: participant labels sit inside a <text class="actor">
    // whose own fill is the box colour; pin the label colour on both levels.
    // Step numbers: a filled accent disc with the canvas colour on top.
    `marker circle{fill:${t.accent} !important;stroke:none !important}.sequenceNumber{fill:${t.bg} !important}`,
    `text.actor,text.actor>tspan,.messageText,.noteText,.labelText,.loopText{fill:${t.ink} !important;stroke:none !important}`,
  ].join("");
}

function mermaidConfig(t) {
  return {
    themeCSS: terminalThemeCss(t),
    // 8px grid, the kit's spacing step.
    flowchart: { htmlLabels: false, useMaxWidth: false, curve: "linear", padding: 16, nodeSpacing: 40, rankSpacing: 48 },
    startOnLoad: false,
    theme: "base",
    darkMode: false, // colours below are explicit per theme; no page detection
    look: "classic", // literal fills that travel with the file (see git history)
    // TOP-LEVEL htmlLabels. Mermaid 11 ignores `flowchart.htmlLabels` for
    // node and subgraph labels, which then come out as <foreignObject> HTML
    // containing `<br>` — not well-formed XML, so an <img> refuses to decode
    // the whole file and the figure is blank. That was "some diagrams don't
    // render". SVG <text> labels have no such failure mode.
    htmlLabels: false,
    sequence: { useMaxWidth: false, boxMargin: 8, messageMargin: 32, mirrorActors: false },
    securityLevel: "strict",
    themeVariables: {
      fontFamily: FONT_FAMILY,
      fontSize: "14px",
      background: t.bg,
      mainBkg: t.surface,
      primaryColor: t.surface,
      primaryTextColor: t.ink,
      primaryBorderColor: t["ink-soft"],
      secondaryColor: t["surface-2"],
      tertiaryColor: t["surface-2"],
      secondaryTextColor: t.ink,
      tertiaryTextColor: t.ink,
      lineColor: t["ink-soft"],
      textColor: t.ink,
      nodeTextColor: t.ink,
      titleColor: t.ink,
      edgeLabelBackground: t.bg,
      clusterBkg: t["surface-2"],
      clusterBorder: t["ink-soft"],
      actorBkg: t.surface,
      actorBorder: t["ink-soft"],
      actorTextColor: t.ink,
      actorLineColor: t["ink-soft"],
      signalColor: t.ink,
      signalTextColor: t.ink,
      labelBoxBkgColor: t.surface,
      labelBoxBorderColor: t["ink-soft"],
      labelTextColor: t.ink,
      loopTextColor: t.ink,
      noteBkgColor: t["surface-2"],
      noteTextColor: t.ink,
      noteBorderColor: t["ink-soft"],
      activationBkgColor: t["surface-2"],
      activationBorderColor: t["ink-soft"],
      sequenceNumberColor: t.bg,
    },
  };
}

const THEMES = [
  { name: "light", suffix: "" },
  { name: "dark", suffix: ".dark" },
];

// --font-render-hinting=none: on Linux, Chromium hints glyphs and rounds
// advance widths to whole pixels (Geist Mono at 14px measures 8px, not 8.4px),
// so mermaid sized every box differently than on macOS and the committed SVGs
// never matched CI's render. Unhinted metrics are fractional on every OS, so
// the output is byte-identical on Linux and macOS. No-op off Linux.
const browser = await chromium.launch({ args: ["--font-render-hinting=none"] });
let written = 0;
try {
  for (const theme of THEMES) {
    const tokens = themeTokens(theme.name);
    const page = await browser.newPage();
    await page.setContent(`<!doctype html><html><head><style>${FONT_FACE}</style></head><body></body></html>`);
    // Measure with the real font: wait until Geist Mono is usable before any
    // getBBox call, or mermaid sizes boxes for the fallback face.
    await page.evaluate(async (family) => {
      await document.fonts.load(`14px ${family}`);
      await document.fonts.ready;
    }, FONT_FAMILY);
    await page.addScriptTag({ content: readFileSync(MERMAID_UMD, "utf8") });
    await page.evaluate((cfg) => window.mermaid.initialize(cfg), mermaidConfig(tokens));

    for (const diagram of diagrams) {
      const result = await page.evaluate(
        async ([id, source, fontFace, bg]) => {
          const { svg } = await window.mermaid.render(`d${id}`, source);
          // Re-serialise through the XML parser so the file is well-formed XML
          // whatever mermaid emitted; a parse error fails the build here rather
          // than shipping a figure an <img> silently cannot decode.
          const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
          const err = doc.querySelector("parsererror");
          if (err) return { error: err.textContent };
          const root = doc.documentElement;
          if (root.querySelector("foreignObject")) return { error: "foreignObject label survived htmlLabels:false" };
          const style = doc.createElementNS("http://www.w3.org/2000/svg", "style");
          style.textContent = `${fontFace} svg{background:${bg}} text,tspan{font-family:"Geist Mono",ui-monospace,monospace !important;}`;
          root.insertBefore(style, root.firstChild);
          root.removeAttribute("style"); // drop max-width; the viewer sizes it
          root.setAttribute("width", "100%");
          return { svg: new XMLSerializer().serializeToString(root) };
        },
        [`${diagram.id}${theme.suffix.replace(".", "_")}`, diagram.source, FONT_FACE, tokens.bg],
      );
      if (result.error || typeof result.svg !== "string") {
        throw new Error(`diagram ${diagram.id} (${theme.name}) did not render: ${result.error ?? "no svg"}`);
      }
      // A viewBox is what lets an SVG scale under the pan-and-zoom viewport.
      if (!/<svg[^>]*\bviewBox=/.test(result.svg)) {
        throw new Error(`diagram ${diagram.id} (${theme.name}) has no viewBox`);
      }
      const file = diagram.file.replace(/\.svg$/, `${theme.suffix}.svg`);
      writeFileSync(join(APP_ROOT, "public", file), result.svg, "utf8");
      written += 1;
    }
    await page.close();
  }
} finally {
  await browser.close();
}

console.log(`book: rendered ${written} diagram file(s) (light + dark) into public/book/diagrams`);
