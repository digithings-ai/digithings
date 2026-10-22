import { showSnapshotError } from "./browser";

/** Shown when `/export` is given a format other than markdown or html. */
export const UNSUPPORTED_EXPORT_FORMAT = "Unsupported format.";

/**
 * `/export`, `/export md`, and `/export markdown` save markdown.
 * `/export html` saves the thread. Anything else shows an error.
 */
export function applyExportSlash(
  format: string,
  doc: Document,
  actions: { html: () => void; markdown: () => void },
): void {
  const value = format.trim().toLowerCase();
  if (value === "html") {
    actions.html();
    return;
  }
  if (value === "" || value === "md" || value === "markdown") {
    actions.markdown();
    return;
  }
  showSnapshotError(doc, UNSUPPORTED_EXPORT_FORMAT);
}
