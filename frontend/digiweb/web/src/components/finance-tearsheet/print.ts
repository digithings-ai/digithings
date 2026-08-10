"use client";
/**
 * The tearsheet PDF pipeline (#1463) — promoted from
 * frontend/digiquant-web/components/tearsheet/print-tearsheet.ts. "Download
 * PDF" is a shipped feature of this family and the reason it is pure SVG:
 * the same chart component instances re-render synchronously at full span
 * (PRINT_FULL_VIEW, linear scale) before the system print dialog opens, so
 * screen and print share ONE render tree. Canvas engines are disqualified
 * on any surface that participates in this export.
 */
import { flushSync } from "react-dom";
import type { ViewWindow } from "./charts";

/** Full backtest window — used when rendering charts for PDF export. */
export const PRINT_FULL_VIEW: ViewWindow = { lo: 0, hi: 1 };

/**
 * Prepare the DOM + React state, invoke the system print dialog, then restore.
 * Uses flushSync so charts re-render at full span before the print layout
 * runs. Pins the light theme for paper output (the print grammar in
 * styles/finance-tearsheet.css pins the light tokens as literals) and tags
 * `html.ts-printing` for print-only rules.
 */
export function runTearsheetPrint(opts: {
  /** document.title while the dialog is open (names the exported PDF). */
  documentTitle: string;
  /** The consumer's `printing` state setter — charts read it to swap to
   *  PRINT_FULL_VIEW / linear scale. */
  setPrinting: (printing: boolean) => void;
}): void {
  const html = document.documentElement;
  const prevTheme = html.getAttribute("data-theme");
  const prevTitle = document.title;

  html.setAttribute("data-theme", "light");
  html.classList.add("ts-printing");
  document.title = opts.documentTitle;

  flushSync(() => opts.setPrinting(true));
  window.print();

  html.classList.remove("ts-printing");
  html.setAttribute("data-theme", prevTheme ?? "dark");
  document.title = prevTitle;
  flushSync(() => opts.setPrinting(false));
}
