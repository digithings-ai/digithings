/** `<deployment>-<YYYY-MM-DD>.html`, UTC calendar day of the export instant. */
export function replayFilename(deployment: string, exportedAt: string): string {
  const slug = deployment
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean)
    .join("-")
    .slice(0, 64);
  const when = new Date(exportedAt);
  const iso = Number.isNaN(when.getTime()) ? new Date() : when;
  const date = iso.toISOString().slice(0, 10);
  return `${slug || "digichat"}-${date}.html`;
}
