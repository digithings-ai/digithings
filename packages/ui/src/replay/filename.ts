import { redactString } from "./redact";

/** `<deployment>-<YYYY-MM-DD-HHMM>-<question>.html`, UTC. */
export function snapshotFilename(
  deployment: string,
  exportedAt: string,
  question: string,
): string {
  const slug = slugPart(deployment) || "digichat";
  const when = new Date(exportedAt);
  const iso = Number.isNaN(when.getTime()) ? new Date() : when;
  const stamp = iso.toISOString();
  const day = stamp.slice(0, 10);
  const hm = `${stamp.slice(11, 13)}${stamp.slice(14, 16)}`;
  const q = slugPart(redactString(question)).slice(0, 48).replace(/-+$/g, "") || "thread";
  return `${slug}-${day}-${hm}-${q}.html`;
}

function slugPart(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
