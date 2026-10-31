// @vitest-environment happy-dom
import { existsSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { allDiagrams, loadChapters } from "./chapters.server";
import { applyDiagramTheme, releaseDiagramObjects, svgDataUrl } from "./diagram-theme";
import { digithingsCsp } from "../security-headers.mjs";

/** A drawing carrying the colours the renderer bakes into each theme's file. */
const LIGHT_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="#0c7c71"/><text fill="#14181b">a</text></svg>';
const DARK_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect fill="#3dd6c4"/><text fill="#eceef0">a</text></svg>';

function figure(src: string): HTMLElement {
  const box = document.createElement("div");
  box.innerHTML = [
    `<img class="book-figure__light" src="${src}" data-diagram-src="${src}">`,
    `<img class="book-figure__dark" src="${src.replace(/\.svg$/, ".dark.svg")}" data-diagram-src="${src.replace(/\.svg$/, ".dark.svg")}">`,
  ].join("");
  document.body.appendChild(box);
  return box;
}

const decoded = (url: string) => decodeURIComponent(url.slice(url.indexOf(",") + 1));

beforeEach(() => {
  releaseDiagramObjects();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => new Response(url.endsWith(".dark.svg") ? DARK_SVG : LIGHT_SVG, { status: 200 })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
  document.documentElement.removeAttribute("data-palette");
});

describe("applyDiagramTheme", () => {
  it("points every diagram at a data: URL, never a blob: one the CSP refuses", async () => {
    const box = figure("/book/diagrams/0123456789abcdef.svg");
    await applyDiagramTheme(box);
    const images = Array.from(box.querySelectorAll("img"));
    expect(images).toHaveLength(2);
    for (const image of images) {
      const src = image.getAttribute("src") ?? "";
      expect(src.startsWith("data:image/svg+xml")).toBe(true);
      expect(src).not.toMatch(/^blob:/);
    }
    // Each theme's file keeps its own drawing: the light one is the light render.
    expect(decoded(images[0].getAttribute("src")!)).toContain("<rect");
  });

  it("redraws in the reader's palette, and redraws again when the palette changes", async () => {
    const box = figure("/book/diagrams/0123456789abcdef.svg");
    const style = document.createElement("style");
    style.textContent = `
      [data-theme="light"] { --accent: #aa0000; --ink: #111111; }
      [data-theme="light"][data-palette="matrix"] { --accent: #00aa00; --ink: #222222; }
    `;
    document.head.appendChild(style);

    await applyDiagramTheme(box);
    const first = decoded(box.querySelector("img")!.getAttribute("src")!);
    expect(first).toContain("#aa0000");
    expect(first).not.toContain("#0c7c71");

    document.documentElement.setAttribute("data-palette", "matrix");
    await applyDiagramTheme(box);
    const second = decoded(box.querySelector("img")!.getAttribute("src")!);
    expect(second).toContain("#00aa00");
    expect(second).not.toContain("#aa0000");
    style.remove();
  });

  it("leaves the committed file in place when it cannot be read", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    const box = figure("/book/diagrams/fedcba9876543210.svg");
    await applyDiagramTheme(box);
    expect(box.querySelector("img")!.getAttribute("src")).toBe("/book/diagrams/fedcba9876543210.svg");
  });
});

describe("the recoloured drawing and the site's CSP", () => {
  it("uses a scheme the page's img-src allows", () => {
    const imgSrc = digithingsCsp()
      .split(";")
      .map((part: string) => part.trim())
      .find((part: string) => part.startsWith("img-src"));
    expect(imgSrc).toBeTruthy();
    const scheme = svgDataUrl("<svg/>").split(":")[0] + ":";
    expect(imgSrc!.split(/\s+/)).toContain(scheme);
  });
});

describe("committed diagrams", () => {
  // A diagram whose fence changed without a re-render is a 404 on the page and
  // a caption with no drawing in the PDF. The book-pdf workflow regenerates
  // them; this keeps the gap from reaching the site between two runs of it.
  it("has a light and a dark file for every mermaid fence in the book", () => {
    const root = process.cwd();
    const missing: string[] = [];
    for (const diagram of allDiagrams(loadChapters(root))) {
      for (const name of [`${diagram.id}.svg`, `${diagram.id}.dark.svg`]) {
        if (!existsSync(join(root, "public", "book", "diagrams", name))) missing.push(name);
      }
    }
    expect(missing).toEqual([]);
  });
});
