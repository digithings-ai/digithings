/**
 * Where a diagram lives — the one piece of the diagram contract a CLIENT
 * component is allowed to know about (DIG-2821).
 *
 * Split out of `diagram.ts` because that module hashes with `node:crypto`, and
 * a browser bundle cannot resolve it. `components/book/BookFigure.tsx` is a
 * client component and it recognises a diagram by its URL prefix; importing
 * the prefix from here keeps `node:crypto` on the build side of the line, which
 * is where the hashing belongs. That import trace is a build error, not a
 * warning — measured, not assumed.
 *
 * Every address in the book is produced by one of these two functions, so the
 * URL a page renders and the path the build writes cannot drift.
 */

/** Directory under `public/` the build writes, relative to that root. */
export const DIAGRAM_PUBLIC_DIR = "book/diagrams";

/** URL prefix the exported site serves that directory from. */
export const DIAGRAM_URL_PREFIX = "/book/diagrams";

/** The public path of a diagram id. One function, so the URL cannot drift. */
export function diagramUrl(id: string): string {
  return `${DIAGRAM_URL_PREFIX}/${id}.svg`;
}

/** The `public/`-relative write path of a diagram id. */
export function diagramFile(id: string): string {
  return `${DIAGRAM_PUBLIC_DIR}/${id}.svg`;
}
