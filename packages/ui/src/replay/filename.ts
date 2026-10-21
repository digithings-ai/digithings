/** `<deployment>-<YYYY-MM-DD>.html`, UTC calendar day of the export instant. */
export function replayFilename(deployment: string, exportedAt: string): string {
  const slug = deployment
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const when = new Date(exportedAt);
  const iso = Number.isNaN(when.getTime()) ? new Date() : when;
  const date = iso.toISOString().slice(0, 10);
  return `${slug || "digichat"}-${date}.html`;
}
