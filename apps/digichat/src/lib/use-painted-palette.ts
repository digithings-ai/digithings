"use client";

/**
 * Whether the document paints a named palette (`data-palette` on <html>).
 *
 * A tenant's brand accent and colours are its default look. A palette the
 * visitor picks with `/theme` (or a parent's, or `?palette=`) brings its own
 * accent, so inline brand styles step aside while one is painted. The server
 * snapshot is "no palette", so hydration matches the first paint and the
 * client re-renders once it reads the attribute.
 */
import { useSyncExternalStore } from "react";

function subscribe(onChange: () => void): () => void {
  if (typeof document === "undefined" || typeof MutationObserver === "undefined") return () => {};
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-palette"] });
  return () => observer.disconnect();
}

export function readPaintsNamedPalette(doc: Document | null = typeof document === "undefined" ? null : document): boolean {
  const value = doc?.documentElement.getAttribute("data-palette");
  return typeof value === "string" && value !== "" && value !== "default";
}

export function usePaintsNamedPalette(): boolean {
  return useSyncExternalStore(subscribe, () => readPaintsNamedPalette(), () => false);
}
