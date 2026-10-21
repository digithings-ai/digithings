import { redactString } from "./redact";

/**
 * `<deployment>-<YYYY-MM-DD-HHMM>-<question>.html`. The time is UTC, so files
 * from different machines sort together. The question is the latest one asked.
 */
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
  const q = questionSlug(question) || "thread";
  return `${slug}-${day}-${hm}-${q}.html`;
}

/**
 * The question as a short slug. File names travel (listings, tickets, mail
 * subjects), so beyond `redactString` any word of 8+ characters that carries
 * a digit (an id, a key the patterns do not know) is dropped, and the slug is
 * cut at a word boundary.
 */
function questionSlug(question: string): string {
  const words = slugPart(redactString(question))
    .split("-")
    .filter((word) => word && !(word.length >= 8 && /\d/.test(word)));
  let out = "";
  for (const word of words) {
    const next = out ? `${out}-${word}` : word;
    if (next.length > 48) break;
    out = next;
  }
  return out;
}

function slugPart(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
