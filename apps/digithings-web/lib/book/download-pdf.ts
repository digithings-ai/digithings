"use client";

import { randomSeed } from "../../components/landing/embedding-map";
import pages from "./generated/pages.json";
import { fieldSvg } from "./field";

/**
 * Build the reader's PDF.
 *
 * The quick path is a file: `book:pdf` prints one edition at build time and
 * records the theme and palette it was printed in. When the reader is on that
 * same theme and palette, the download is a fetch of the file that already
 * exists — no rendering at all.
 *
 * Any other theme or palette is built from the pages already on screen. The
 * reader has paginated them; re-opening the print route in an iframe and
 * paginating again cost six seconds before a single pixel was captured, which
 * is most of why the button felt broken. Capturing the live page boxes skips
 * it: the pages are the same nodes, and their styles are already applied.
 */
export type BuildProgress = { done: number; total: number };

const A4 = { width: 595.28, height: 841.89 };
/** 794 CSS px wide at 1.25 gives ~993 px: legible on screen, and the
 * dominant cost of this build is pixels, not pages. */
const CAPTURE_SCALE = 1.25;
const CAPTURE_QUALITY = 0.8;

function currentTheme(): string {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

function currentPalette(): string {
  return document.documentElement.getAttribute("data-palette") ?? "";
}

type PrintedEdition = { palette: string; theme: string; file: string };

/** The editions `book:pdf` printed at build time, if it recorded any. */
function printedEdition(): PrintedEdition | undefined {
  const list = (pages as { editions?: PrintedEdition[] }).editions ?? [];
  const theme = currentTheme();
  const palette = currentPalette();
  return list.find((entry) => entry.theme === theme && entry.palette === palette);
}

async function fetchPrintedEdition(edition: PrintedEdition): Promise<{
  blob: Blob;
  filename: string;
  pages: number;
}> {
  const response = await fetch(`/book/${edition.file}`);
  if (!response.ok) throw new Error("the printed edition could not be read");
  return {
    blob: await response.blob(),
    filename: `the-digithings-book-${currentTheme()}${currentPalette() ? `-${currentPalette()}` : ""}.pdf`,
    pages: pages.pages,
  };
}

export async function buildBookPdf(
  onProgress?: (progress: BuildProgress) => void,
): Promise<{ blob: Blob; filename: string; pages: number }> {
  const printed = printedEdition();
  if (printed) return fetchPrintedEdition(printed);

  const theme = currentTheme();
  const palette = currentPalette();
  const nodes = [...document.querySelectorAll<HTMLElement>(".book-live .pagedjs_page")];
  if (nodes.length < 1) throw new Error("the book has not paginated yet");

  const stage = document.querySelector<HTMLElement>(".book-live__stage");
  const priorTransform = stage?.style.transform ?? "";
  const prior: { margin: string; padding: string; border: string }[] = [];
  const added: HTMLElement[] = [];

  try {
    // The reader fits the pages to its column with a scale; the export wants
    // the page at its own size. The margins and rules between sheets are the
    // reader's, not the book's.
    if (stage) stage.style.transform = "none";
    for (const node of nodes) {
      prior.push({
        margin: node.style.margin,
        padding: node.style.padding,
        border: node.style.border,
      });
      node.style.margin = "0";
      node.style.padding = "0";
      node.style.border = "0";
    }

    // A field is drawn once, as a still: the page has an animated canvas, and
    // a capture of it depends on the frame the browser happened to be on.
    for (const node of nodes) {
      if (
        !node.querySelector(".book-cover") &&
        !node.querySelector(".book-contents") &&
        !node.querySelector(".book-colophon")
      ) {
        continue;
      }
      const isCover = Boolean(node.querySelector(".book-cover"));
      const isContents = Boolean(node.querySelector(".book-contents"));
      const light = theme === "light";
      const layer = document.createElement("div");
      layer.className = "book-field";
      layer.setAttribute("aria-hidden", "true");
      layer.style.cssText = `position:absolute;inset:0;z-index:0;pointer-events:none;opacity:${
        isCover ? (light ? 0.5 : 0.82) : isContents ? (light ? 0.18 : 0.4) : light ? 0.3 : 0.55
      }`;
      layer.innerHTML = fieldSvg({
        seed: randomSeed(),
        time: 2600 + Math.floor(Math.random() * 18_000),
        strength: light ? 1.3 : isCover ? 1.7 : 1.45,
      });
      node.prepend(layer);
      added.push(layer);
      const sheet = node.querySelector<HTMLElement>(".pagedjs_sheet");
      if (sheet) {
        sheet.style.position = "relative";
        sheet.style.zIndex = "1";
      }
    }

    // Continuation pages need the chapter name at the top. A page that starts a
    // chapter already carries the title; every later page of that chapter gets
    // a quiet running head.
    let runningChapter = "";
    for (const node of nodes) {
      if (node.querySelector(".book-cover, .book-contents, .book-colophon, .book-end")) continue;
      const heads = node.querySelectorAll(".book-chapter__head h2");
      const title = heads[heads.length - 1]?.textContent?.trim() ?? "";
      if (title) {
        runningChapter = title;
        continue;
      }
      if (!runningChapter) continue;
      const head = document.createElement("div");
      head.className = "book-running-head";
      head.textContent = runningChapter;
      node.append(head);
      added.push(head);
    }

    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));

    const { domToJpeg } = await import("modern-screenshot");
    const { PDFDocument } = await import("pdf-lib");
    const pdf = await PDFDocument.create();
    pdf.setTitle("The digithings book");
    pdf.setAuthor("digithings");
    pdf.setSubject("Self-hosted AI infrastructure: why it matters, how it scales, and what it costs.");
    pdf.setCreator(`digithings.ai/book · ${theme}${palette ? ` · ${palette}` : ""}`);

    const body = getComputedStyle(document.body);
    const root = getComputedStyle(document.documentElement);
    const transparent = "rgba(0, 0, 0, 0)"; // canon-allow: computed-style comparison, not a painted colour
    const background =
      body.backgroundColor !== transparent
        ? body.backgroundColor
        : root.getPropertyValue("--bg").trim() || "transparent";

    // One raster pass over the whole book, then a slice per page.
    //
    // Capturing each page on its own re-embeds the document's fonts and images
    // every time — nineteen passes of that cost twenty-two seconds, and no
    // amount of lowering the scale changed it. The cost is per call, not per
    // pixel. One tall strip costs one call; the slicing after it is a canvas
    // draw per page and takes milliseconds.
    const pageHeight = nodes[0]?.getBoundingClientRect().height ?? 1123;
    const t0 = performance.now();
    const strip = document.createElement("div");
    strip.style.cssText = `position:fixed;left:-20000px;top:0;width:794px;background:${background}`;
    document.body.appendChild(strip);
    const slices: { top: number; height: number }[] = [];
    let offset = 0;
    try {
      for (const node of nodes) {
        const clone = node.cloneNode(true) as HTMLElement;
        clone.style.margin = "0";
        clone.style.padding = "0";
        clone.style.border = "0";
        strip.appendChild(clone);
        slices.push({ top: offset, height: pageHeight });
        offset += pageHeight;
      }

      onProgress?.({ done: 0, total: nodes.length });
      const { domToJpeg } = await import("modern-screenshot");
      const t1 = performance.now();
      const stripData = await domToJpeg(strip, {
        scale: CAPTURE_SCALE,
        quality: 1,
        backgroundColor: background,
      });
      const t2 = performance.now();
      const bitmap = await createImageBitmap(await (await fetch(stripData)).blob());
      console.log("[pdf] clone", Math.round(t1-t0), "raster", Math.round(t2-t1));
      const { PDFDocument } = await import("pdf-lib");
      const pdf = await PDFDocument.create();
      pdf.setTitle("The digithings book");
      pdf.setAuthor("digithings");
      pdf.setSubject("Self-hosted AI infrastructure: why it matters, how it scales, and what it costs.");
      pdf.setCreator(`digithings.ai/book · ${theme}${palette ? ` · ${palette}` : ""}`);

      for (let index = 0; index < slices.length; index += 1) {
        const slice = slices[index];
        if (!slice) continue;
        onProgress?.({ done: index, total: slices.length });
        const canvas = document.createElement("canvas");
        canvas.width = Math.round(794 * CAPTURE_SCALE);
        canvas.height = Math.round(slice.height * CAPTURE_SCALE);
        const context = canvas.getContext("2d");
        if (!context) throw new Error("the page could not be drawn");
        context.drawImage(
          bitmap,
          0,
          Math.round(slice.top * CAPTURE_SCALE),
          canvas.width,
          canvas.height,
          0,
          0,
          canvas.width,
          canvas.height,
        );
        const dataUrl = canvas.toDataURL("image/jpeg", CAPTURE_QUALITY);
        const jpeg = await (await fetch(dataUrl)).arrayBuffer();
        const image = await pdf.embedJpg(jpeg);
        const landscape = image.width > image.height;
        const width = landscape ? A4.height : A4.width;
        const height = landscape ? A4.width : A4.height;
        const sheet = pdf.addPage([width, height]);
        sheet.drawImage(image, { x: 0, y: 0, width, height });
      }

      console.log("[pdf] slices", Math.round(performance.now()-t2));
      onProgress?.({ done: slices.length, total: slices.length });
      const bytes = await pdf.save();
      return {
        blob: new Blob([new Uint8Array(bytes)], { type: "application/pdf" }),
        filename: `the-digithings-book-${theme}${palette ? `-${palette}` : ""}.pdf`,
        pages: slices.length,
      };
    } finally {
      strip.remove();
    }

  } finally {
    for (const layer of added) layer.remove();
    if (stage) stage.style.transform = priorTransform;
    nodes.forEach((node, index) => {
      const style = prior[index];
      if (!style) return;
      node.style.margin = style.margin;
      node.style.padding = style.padding;
      node.style.border = style.border;
    });
  }
}
