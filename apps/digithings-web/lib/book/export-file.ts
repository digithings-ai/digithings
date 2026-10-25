"use client";

/**
 * Shared bits of the book's exports: what the file is called, and how it is
 * handed to the browser.
 *
 * The name carries the theme and palette because the file does: a dark-monokai
 * PDF and a light one are different artefacts, and a folder holding both should
 * say which is which without being opened.
 */

export type BookAppearance = { theme: "light" | "dark"; palette: string };

export function bookAppearance(): BookAppearance {
  const theme = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  const palette = document.documentElement.getAttribute("data-palette") ?? "";
  return { theme, palette };
}

/** `the-digithings-book-<theme>[-<palette>].<extension>` */
export function bookFilename(extension: string, appearance = bookAppearance()): string {
  return `the-digithings-book-${appearance.theme}${appearance.palette ? `-${appearance.palette}` : ""}.${extension}`;
}

/**
 * Save a blob the way every export here does it: an object URL, a synthetic
 * link, and a revocation late enough that the browser has started the write.
 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
