// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { themeInitScript } from "@digithings/ui";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * The theme has to be on <html> before the first frame, or the boot loader
 * paints the server default (dark, no palette) and the chat then repaints in
 * the saved palette. next/script "beforeInteractive" in the App Router queues
 * the body into self.__next_s and runs it only after the Next runtime loads,
 * so the root layout must ship the scripts as plain inline <head> scripts.
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(here, "layout.tsx"), "utf8");

describe("digichat root layout pre-paint theme", () => {
  it("does not defer the theme scripts through next/script", () => {
    expect(src).not.toMatch(/^import\s+Script\s+from\s+"next\/script"/m);
    expect(src).not.toMatch(/strategy="beforeInteractive"/);
  });

  it("inlines themeInitScript, the favicon and the class sync in <head>, before <body>", () => {
    const head = src.search(/^\s*<head>/m);
    const headEnd = src.indexOf("</head>");
    const body = src.search(/<body\s+className/);
    expect(head).toBeGreaterThan(-1);
    expect(headEnd).toBeGreaterThan(head);
    expect(body).toBeGreaterThan(headEnd);
    const block = src.slice(head, headEnd);
    const order = ["__html: themeInitScript", "__html: faviconInit", "__html: themeClassSyncScript"].map((s) =>
      block.indexOf(s),
    );
    expect(order.every((i) => i > -1)).toBe(true);
    expect(order).toEqual([...order].sort((a, b) => a - b));
    expect(block).toMatch(/<script\s+id="digichat-theme-init"/);
  });
});

describe("themeInitScript (what the head script paints)", () => {
  afterEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("data-palette");
    vi.unstubAllGlobals();
  });

  const run = (light: boolean) => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: light && q.includes("light") }) as MediaQueryList);
    new Function(themeInitScript)();
    return document.documentElement;
  };

  it("follows the OS scheme with no saved choice, default palette", () => {
    expect(run(true).getAttribute("data-theme")).toBe("light");
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
    expect(run(false).getAttribute("data-theme")).toBe("dark");
  });

  it("applies a palette the site saved", () => {
    localStorage.setItem("dt-palette", "nord");
    const e = run(false);
    expect(e.getAttribute("data-theme")).toBe("dark");
    expect(e.getAttribute("data-palette")).toBe("nord");
  });
});
