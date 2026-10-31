"use client";

/**
 * One self-contained `.html` file of the book — the pages, as pages.
 *
 * The source is the paginated DOM the reader is already looking at: the same
 * page boxes the PDF is captured from, already carrying the reader's theme. So
 * the export is not a second rendering that could drift from the screen, it is
 * the screen, flattened into a file.
 *
 * "Self-contained" is the requirement, and it is the hard part:
 *
 *  - every stylesheet the page boxes are painted with is inlined as text, so
 *    the file opens on a machine with no network and no site;
 *  - the fonts those stylesheets reference are inlined as data URLs, because a
 *    stylesheet that points at `/_next/static/media/...` is an external fetch
 *    the moment the file is opened somewhere else;
 *  - the figures are already `data:` URLs (the reader's recoloured drawings,
 *    `lib/book/diagram-theme`), so they travel as they are; any other image is
 *    fetched and re-encoded into the file as a data URL. A `data:` source is
 *    never re-fetched: the site's CSP has no `data:` in `connect-src`, and the
 *    refused fetch used to drop every figure from the file.
 *
 * The paged stylesheets (`PAGED_CSS`, `PRINT_CSS`) are appended by name rather
 * than trusted to appear in the captured set: they are the book's typography
 * and its page geometry, and an export missing them would open as unstyled
 * prose in the right order.
 */
import { bookFilename } from "./export-file";
import { PAGED_CSS, PRINT_CSS } from "./printCss";

/**
 * The tokens the book paints with. Snapshotted from the live root, because the
 * exported file cannot inherit a theme it is no longer attached to.
 */
const TOKENS = [
  "--ink",
  "--ink-soft",
  "--bg",
  "--hair",
  "--accent",
  "--color-ink",
  "--color-ink-soft",
  "--color-hair",
  "--font-sans",
  "--font-mono",
  "--font-display",
  "--font-stack-mono",
  "--wrap",
  "--gutter",
];

/** Export-only page furniture: the sheets on a neutral ground. */
const PAPER_CSS = `
html, body { margin: 0; padding: 0; background: var(--bg); }
body {
  color: var(--ink);
  font-family: var(--font-sans), ui-monospace, monospace;
  padding: 2rem 1rem 3rem;
}
.book-export__sheet {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2rem;
}
.book-export__sheet > .pagedjs_page {
  margin: 0;
  border: 1px solid var(--hair);
}
@media print {
  body { padding: 0; }
  .book-export__sheet { gap: 0; }
  .book-export__sheet > .pagedjs_page {
    border: 0;
    break-after: page;
    break-inside: avoid;
  }
  .book-export__sheet > .pagedjs_page:last-child { break-after: auto; }
}
`;

function encoder(): (bytes: Uint8Array) => string {
  // Chunked on purpose: spreading a megabyte of bytes into `String.fromCharCode`
  // overflows the argument limit.
  return (bytes) => {
    let binary = "";
    const chunk = 0x8000;
    for (let index = 0; index < bytes.length; index += chunk) {
      binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
    }
    return btoa(binary);
  };
}

async function toDataUrl(url: string): Promise<string | null> {
  if (url.startsWith("data:")) return url;
  try {
    const response = await fetch(url);
    if (!response.ok) {
      console.error(`book: ${url.slice(0, 40)} answered ${response.status}`);
      return null;
    }
    const type = response.headers.get("content-type") ?? "application/octet-stream";
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes.length === 0) return null;
    return `data:${type};base64,${encoder()(bytes)}`;
  } catch (error) {
    console.error(`book: could not read ${url.slice(0, 40)}`, error);
    return null;
  }
}

/** Every rule the live document is painted with, as text. */
function capturedCss(): string {
  const parts: string[] = [];
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      parts.push(
        Array.from(sheet.cssRules)
          .map((rule) => rule.cssText)
          .join("\n"),
      );
    } catch {
      // A cross-origin sheet cannot be read. There are none here; a future one
      // must fall back to the paged sheets above rather than fail the export.
    }
  }
  return parts.join("\n");
}

/** Replace every same-origin font reference with the font itself. */
async function inlineFonts(css: string): Promise<string> {
  if (!css.includes("@font-face")) return css;
  const blocks = css.match(/@font-face\s*\{[^}]*\}/g) ?? [];
  let out = css;
  for (const block of blocks) {
    const match = block.match(/url\((['"]?)([^'")]+)\1\)/);
    const url = match?.[2];
    if (!url || url.startsWith("data:")) continue;
    const dataUrl = await toDataUrl(url);
    // A font that cannot be read is dropped: the stacks all end in a system
    // font, so the file still reads correctly, and it still needs no network.
    out = out.split(block).join(dataUrl ? block.split(url).join(dataUrl) : "");
  }
  return out;
}

function tokenBlock(): string {
  const style = getComputedStyle(document.documentElement);
  const declarations = TOKENS.map((token) => {
    const value = style.getPropertyValue(token).trim();
    return value ? `  ${token}: ${value};` : "";
  }).filter(Boolean);
  const theme = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  return `:root {\n  color-scheme: ${theme};\n${declarations.join("\n")}\n}`;
}

const STRIPPED_ATTRIBUTES = ["data-ref", "data-nth-of-type", "srcset", "sizes", "loading", "decoding"];

/**
 * The page boxes, cleaned for a life outside this page: measurement copies
 * gone, internal ids gone, crop marks gone, figures and fonts inside.
 */
async function pageBoxes(): Promise<string> {
  const source =
    document.querySelector<HTMLElement>(".book-live__stage") ??
    document.querySelector<HTMLElement>(".pagedjs_pages");
  if (!source || !source.querySelector(".pagedjs_page")) throw new Error("the book has not paginated yet");

  // Clone, never move: the reader is still using these boxes.
  const clone = source.cloneNode(true) as HTMLElement;
  clone.removeAttribute("style");
  clone.className = "book-export__sheet";

  // Not `[data-undisplayed]`: pagedjs marks the nodes it re-displays inside a
  // page box with it (the diagram viewports are), so removing them removes the
  // figures. The measurement copies it also marks are hidden by the book's own
  // stylesheet, which travels with this file.
  clone.querySelectorAll("script, noscript, .pagedjs_bleed").forEach((node) => node.remove());

  // pagedjs clones the pagination host itself into a page box when the host IS
  // that page's body, and the host carries the off-screen measurement style:
  // `position: fixed` escapes the page box and paints the page's words over the
  // whole file. The wrapper means nothing outside the reader, so it goes, and
  // the copied style with it.
  for (const wrapper of Array.from(clone.querySelectorAll(".book-live__source"))) {
    wrapper.replaceWith(...Array.from(wrapper.childNodes));
  }
  for (const node of Array.from(clone.querySelectorAll<HTMLElement>('[style*="position: fixed"], [style*="position:fixed"]'))) {
    node.style.position = "";
    node.style.left = "";
    node.style.top = "";
  }
  clone.querySelectorAll("[data-book-anchor]").forEach((node) => node.remove());
  for (const node of Array.from(clone.querySelectorAll("*"))) {
    for (const name of STRIPPED_ATTRIBUTES) node.removeAttribute(name);
  }

  for (const image of Array.from(clone.querySelectorAll("img"))) {
    const source = image.getAttribute("src") ?? "";
    if (!source) continue;
    const dataUrl = await toDataUrl(source);
    if (dataUrl) {
      image.setAttribute("src", dataUrl);
      continue;
    }
    // Nothing to show and no way to fetch it later: keep the words, drop the
    // frame, so the export has no broken image in it.
    const note = document.createElement("span");
    note.textContent = image.getAttribute("alt") ?? "";
    image.replaceWith(note);
  }

  return clone.outerHTML;
}

export async function buildBookHtml(): Promise<{ blob: Blob; filename: string; bytes: number }> {
  const [pages, fonts] = await Promise.all([pageBoxes(), inlineFonts(capturedCss())]);
  const theme = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  const palette = document.documentElement.getAttribute("data-palette") ?? "";

  const html = [
    "<!doctype html>",
    `<html lang="en" data-theme="${theme}"${palette ? ` data-palette="${palette}"` : ""}>`,
    "<head>",
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    "<title>the digithings book</title>",
    `<meta name="generator" content="digithings.ai/book">`,
    `<style>\n${tokenBlock()}\n</style>`,
    `<style>\n${PAGED_CSS}\n</style>`,
    `<style>\n${PRINT_CSS}\n</style>`,
    `<style>\n${fonts}\n</style>`,
    `<style>\n${PAPER_CSS}\n</style>`,
    "</head>",
    "<body>",
    pages,
    "</body>",
    "</html>",
  ].join("\n");

  return {
    blob: new Blob([html], { type: "text/html;charset=utf-8" }),
    filename: bookFilename("html"),
    bytes: html.length,
  };
}
