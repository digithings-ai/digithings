"use client";

import { randomSeed } from "../../components/landing/embedding-map";
import { fieldSvg } from "./field";

/**
 * Build the reader's PDF in the browser.
 *
 * The site is a static export, so a fixed `/book/*.pdf` cannot be random per
 * download. This opens the real paginated print route in an off-screen iframe,
 * applies the reader's current theme and palette, paints a fresh embedding
 * field behind the cover, contents and closing page only, then captures the
 * finished page boxes and assembles them with pdf-lib. A field on a chapter
 * opener read as a cutout behind the title, so text pages stay clean.
 */
export type BuildProgress = { done: number; total: number };

const A4 = { width: 595.28, height: 841.89 };

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function waitFor<T>(read: () => T | null, timeoutMs: number): Promise<T> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const value = read();
    if (value) return value;
    await sleep(120);
  }
  throw new Error("the book took too long to paginate");
}

export async function buildBookPdf(
  onProgress?: (progress: BuildProgress) => void,
): Promise<{ blob: Blob; filename: string; pages: number }> {
  const theme = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  const palette = document.documentElement.getAttribute("data-palette") ?? "";
  const iframe = document.createElement("iframe");
  iframe.setAttribute("aria-hidden", "true");
  iframe.tabIndex = -1;
  iframe.style.cssText =
    "position:fixed;left:-12000px;top:0;width:900px;height:1200px;border:0;";
  iframe.src = "/book/print/";

  try {
    document.body.appendChild(iframe);
    await new Promise<void>((resolve, reject) => {
      iframe.onload = () => resolve();
      iframe.onerror = () => reject(new Error("the print page could not load"));
    });
    const frame = iframe.contentDocument;
    const win = iframe.contentWindow;
    if (!frame || !win) throw new Error("the print page could not be reached");

    // The print route reads the platform theme from the same storage, but the
    // iframe may hydrate before the reader's palette is painted. Set both
    // attributes explicitly so the captured pages match what is on screen.
    frame.documentElement.setAttribute("data-theme", theme);
    if (palette) frame.documentElement.setAttribute("data-palette", palette);
    else frame.documentElement.removeAttribute("data-palette");
    await win.document.fonts.ready;

    await waitFor(() => frame.querySelector("[data-book-paginated]"), 120_000);
    const pages = [...frame.querySelectorAll<HTMLElement>(".pagedjs_page")];
    if (pages.length < 1) throw new Error("the book paginated to zero pages");

    const fields = pages.filter(
      (page) =>
        page.querySelector(".book-cover") ||
        page.querySelector(".book-contents") ||
        page.querySelector(".book-end"),
    );
    for (const page of fields) {
      const isCover = Boolean(page.querySelector(".book-cover"));
      const isContents = Boolean(page.querySelector(".book-contents"));
      const isEnd = Boolean(page.querySelector(".book-end"));
      page.querySelectorAll(".book-cover__field").forEach((node) => node.remove());
      const layer = frame.createElement("div");
      layer.className = "book-field";
      layer.setAttribute("aria-hidden", "true");
      const light = theme === "light";
      layer.style.cssText = `position:absolute;inset:0;z-index:0;pointer-events:none;opacity:${
        isCover ? (light ? 0.5 : 0.82) : isContents ? (light ? 0.18 : 0.4) : isEnd ? (light ? 0.42 : 0.62) : light ? 0.14 : 0.3
      }`;
      layer.innerHTML = fieldSvg({
        seed: randomSeed(),
        time: 2600 + Math.floor(Math.random() * 18_000),
        strength: light ? 1.3 : isCover ? 1.7 : 1.45,
      });
      page.prepend(layer);
      const sheet = page.querySelector<HTMLElement>(".pagedjs_sheet");
      if (sheet) {
        sheet.style.position = "relative";
        sheet.style.zIndex = "1";
      }
    }
    // Continuation pages need the chapter name at the top. A page that starts
    // a chapter already carries the title; every later page of that chapter
    // gets a quiet running head, so the reader never lands on an orphaned
    // "Trade-offs" with no idea which chapter it belongs to.
    let runningChapter = "";
    for (const page of pages) {
      if (page.querySelector(".book-cover, .book-contents, .book-colophon, .book-end")) continue;
      const title = page.querySelector(".book-chapter__head h2")?.textContent?.trim() ?? "";
      if (title) {
        runningChapter = title;
        continue;
      }
      if (!runningChapter) continue;
      const head = frame.createElement("div");
      head.className = "book-running-head";
      head.textContent = runningChapter;
      page.append(head);
    }

    await new Promise((resolve) => win.requestAnimationFrame(() => resolve(null)));

    const { domToJpeg } = await import("modern-screenshot");
    const { PDFDocument } = await import("pdf-lib");
    const pdf = await PDFDocument.create();
    pdf.setTitle("The digithings book");
    pdf.setAuthor("digithings");
    pdf.setSubject("Self-hosted AI infrastructure: why it matters, how it scales, and what it costs.");
    pdf.setCreator(`digithings.ai/book · ${theme}${palette ? ` · ${palette}` : ""}`);

    const body = win.getComputedStyle(frame.body);
    const root = win.getComputedStyle(frame.documentElement);
    const transparent = "rgba(0, 0, 0, 0)"; // canon-allow: computed-style comparison, not a painted colour
    const background =
      body.backgroundColor !== transparent
        ? body.backgroundColor
        : root.getPropertyValue("--bg").trim() || "transparent";

    for (let index = 0; index < pages.length; index += 1) {
      const page = pages[index];
      if (!page) continue;
      onProgress?.({ done: index, total: pages.length });
      const dataUrl = await domToJpeg(page, {
        quality: 0.82,
        scale: 1.25,
        backgroundColor: background,
      });
      const jpeg = await (await fetch(dataUrl)).arrayBuffer();
      const image = await pdf.embedJpg(jpeg);
      // Diagram plates are landscape page boxes; every other page is A4.
      const landscape = image.width > image.height;
      const width = landscape ? A4.height : A4.width;
      const height = landscape ? A4.width : A4.height;
      const sheet = pdf.addPage([width, height]);
      sheet.drawImage(image, { x: 0, y: 0, width, height });
      await sleep(0);
    }

    onProgress?.({ done: pages.length, total: pages.length });
    const bytes = await pdf.save();
    return {
      blob: new Blob([new Uint8Array(bytes)], { type: "application/pdf" }),
      filename: `the-digithings-book-${theme}${palette ? `-${palette}` : ""}.pdf`,
      pages: pages.length,
    };
  } finally {
    iframe.remove();
  }
}
