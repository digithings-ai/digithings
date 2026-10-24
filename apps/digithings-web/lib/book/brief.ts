/**
 * The brief edition: the chapters the printed book carries, in reading order.
 *
 * The web keeps every chapter in `order:` sequence. Paper is the argument for a
 * client or partner, read in half an hour, and its sequence is editorial: the
 * case first (why it lives anywhere, why it is open, how it scales, what it
 * builds), then the modules a reader meets in that case, then where to start.
 * That is why this is an ordered list and not a filter over `order:`.
 *
 * Each chapter is written to fill exactly its pages in print (one page, two
 * for the use cases). A chapter added here needs the same fitting pass.
 *
 * digivoice is deliberately absent. It is a utility rather than a vertical:
 * it has no conversation of its own and no place of its own in the stack, and
 * it belongs in the print argument as a capability of the interface, not as a
 * chapter beside the modules. The web chapter carries the depth.
 */
export const BRIEF: readonly string[] = [
  "01-why-a-book",
  "02-why-self-hosted",
  "03-open-core",
  "03-how-it-scales",
  "05-environment",
  "06-use-cases",
  "10-digigraph",
  "11-digillm",
  "20-mcp",
  "17-digisearch",
  "13-digiquant",
  "12-digichat",
  "15-digikey",
  "16-digitrace",
  "19-local-stack",
  "23-self-hosting",
];

/**
 * The brief's chapters, in brief order. A slug in the list with no chapter
 * behind it throws: a silently shorter book is the failure this prevents.
 */
export function briefChapters<T extends { slug: string }>(chapters: readonly T[]): T[] {
  const bySlug = new Map(chapters.map((chapter) => [chapter.slug, chapter]));
  return BRIEF.map((slug) => {
    const chapter = bySlug.get(slug);
    if (!chapter) throw new Error(`book: the brief names "${slug}", which is not a published chapter`);
    return chapter;
  });
}
