/**
 * Heading slugs and anchors for the book (DIG-2821).
 *
 * One rule, used by three consumers that must agree exactly: the chapter page
 * writes `id="…"` onto each heading, the table of contents links to those ids,
 * and the PDF's running header resolves a page number from them. A slug that
 * is computed twice must come out the same twice, so this is one pure function
 * and nothing else is allowed to invent an id.
 *
 * MDX lets a heading carry its own `{#custom-id}`. When it does, that id wins —
 * otherwise a cross-chapter link written before a heading was renamed would
 * break on rename. The override is consumed here and stripped, so no consumer
 * sees the braces.
 */

/** The slug alphabet: lowercase ascii letters, digits and single hyphens. */
const SLUG_STRIP = /[^a-z0-9]+/g;

/** `{#custom-id}` (or `{#custom-id}` on its own line) at the end of a heading. */
const ID_OVERRIDE = /\s*\{#([A-Za-z][A-Za-z0-9_-]*)\}\s*$/;

/** `## Heading` — ATX only. Setext headings are not supported in the book. */
const ATX_HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;

/** Markdown inline emphasis/link punctuation that is not part of the words. */
const MARKDOWN_NOISE = /[*_`~]/g;

export interface Heading {
  /** Heading level, 2–4 in practice; 1 is the chapter title. */
  level: number;
  /** The heading's plain text, override consumed and markdown noise removed. */
  text: string;
  /** The `id` this heading is rendered with — what the ToC links to. */
  id: string;
}

/** Strip markdown inline noise so a heading reads as words, not as source. */
export function headingText(raw: string): string {
  return raw
    .replace(MARKDOWN_NOISE, "")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .trim();
}

/**
 * Slug a heading's text.
 *
 * Accented letters are folded to their ascii base (`é` → `e`) so a chapter
 * written in a European language still produces a linkable, typeable anchor.
 * An empty result (a heading of only punctuation) becomes `section`, which is
 * stable and therefore still a valid anchor rather than a duplicate `""`.
 */
export function slugify(text: string): string {
  const folded = text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  const slug = folded.replace(SLUG_STRIP, "-").replace(/^-+|-+$/g, "");
  return slug === "" ? "section" : slug;
}

/**
 * Take a heading's explicit `{#id}` if it has one.
 *
 * Returns `null` when the heading carries no override, so the caller can tell
 * "author chose this id" from "we derived one" — the two need different
 * collision handling.
 */
export function takeIdOverride(raw: string): { text: string; id: string | null } {
  const m = ID_OVERRIDE.exec(raw);
  if (!m) return { text: raw, id: null };
  return { text: raw.slice(0, m.index), id: m[1] };
}

/**
 * Extract every heading from a chapter body, in document order, with ids that
 * are unique within the body.
 *
 * A repeated heading gets `-2`, `-3`… in document order, which is what makes a
 * duplicated `## Notes` heading produce two working ToC entries instead of one
 * dead link.
 */
export function extractHeadings(body: string): Heading[] {
  const seen = new Map<string, number>();
  const out: Heading[] = [];
  // Fenced code is skipped: a `# comment` inside a ```sh block is not a heading.
  // The opening fence's FULL run is remembered, not just its character: a
  // ```` fence is closed only by a run at least as long, so a ``` line inside
  // it is code and not the end of the block.
  let openMarker: string | null = null;
  for (const line of body.split("\n")) {
    const fenceMatch = /^(\s*)(`{3,}|~{3,})/.exec(line);
    if (fenceMatch) {
      const marker = fenceMatch[2];
      if (openMarker === null) {
        openMarker = marker;
      } else if (marker[0] === openMarker[0] && marker.length >= openMarker.length) {
        openMarker = null;
      }
      continue;
    }
    if (openMarker !== null) continue;
    const m = ATX_HEADING.exec(line);
    if (!m) continue;
    const { text: raw, id: override } = takeIdOverride(m[2]);
    const text = headingText(raw);
    const base = override ?? slugify(text);
    const count = (seen.get(base) ?? 0) + 1;
    seen.set(base, count);
    out.push({ level: m[1].length, text, id: count === 1 ? base : `${base}-${count}` });
  }
  return out;
}