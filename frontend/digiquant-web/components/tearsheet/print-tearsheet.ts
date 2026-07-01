import { flushSync } from "react-dom";
import type { ViewWindow } from "./charts";

/** Full backtest window — used when rendering charts for PDF export. */
export const PRINT_FULL_VIEW: ViewWindow = { lo: 0, hi: 1 };

export function printDocumentTitle(strategyTitle: string): string {
  return `${strategyTitle} — DigiQuant`;
}

/**
 * Prepare the DOM + React state, invoke the system print dialog, then restore.
 * Uses flushSync so charts re-render at full span before the print layout runs.
 */
export function runPrintTearsheet(opts: {
  strategyTitle: string;
  setPrinting: (printing: boolean) => void;
}): void {
  const html = document.documentElement;
  const prevTheme = html.getAttribute("data-theme");
  const prevTitle = document.title;

  html.setAttribute("data-theme", "light");
  html.classList.add("ts-printing");
  document.title = printDocumentTitle(opts.strategyTitle);

  flushSync(() => opts.setPrinting(true));
  window.print();

  html.classList.remove("ts-printing");
  html.setAttribute("data-theme", prevTheme ?? "dark");
  document.title = prevTitle;
  flushSync(() => opts.setPrinting(false));
}
