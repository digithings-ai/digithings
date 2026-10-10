import BookToc from "@/components/book/BookToc";
import PagedBoot from "@/components/book/PagedBoot";
import { chapterRefs, loadChapters } from "@/lib/book/chapters.server";

/**
 * The whole book as one continuous document — the thing that gets printed
 * (DIG-2821).
 *
 * Why one page and not "print each chapter": the printed book needs running
 * headers that change per chapter, page numbers that are continuous across the
 * volume, and a front table of contents whose page references were resolved
 * from the SAME pagination that produced those numbers. Splitting the print
 * into per-chapter pages gives three separate documents, and a page reference
 * in one of them means nothing to the reader holding a different one.
 */
export default async function BookPrintPage() {
  const chapters = loadChapters(process.cwd());
  const refs = chapterRefs(chapters);

  // Loaded up front, before any JSX: a chapter that will not compile must fail
  // the build, not render an empty section in the middle of a printed page.
  const bodies = await Promise.all(
    chapters.map(async (chapter) => {
      const mod = (await import(`../../../content/book/${chapter.slug}.mdx`)) as {
        default: () => React.JSX.Element;
      };
      return { slug: chapter.slug, Body: mod.default };
    }),
  );

  return (
    // `data-paged-content` is what PagedBoot hands the chunker: this element
    // becomes the paginated document. The site nav and footer sit outside it.
    <div data-paged-content="book" className="mx-auto w-full max-w-[var(--wrap)] px-[var(--gutter)]">
      <PagedBoot enabled />

      <div className="book-print-only running-element">
        <span>the digithings book</span>
        <span>digithings.ai/book</span>
      </div>

      <h1 className="mt-10 mb-2 font-display text-[clamp(2rem,4vw,3rem)] tracking-[-0.02em] text-ink">
        The digithings book
      </h1>
      <p className="mb-8 max-w-[64ch] text-[1.05rem] text-ink-soft">
        Printed from the same files the web pages are built from.
      </p>

      {/* Front matter. The reference beside each chapter is filled in by
          PagedBoot, after the engine has decided where the pages break — a
          number written here would be wrong the moment a paragraph grew a
          line. */}
      <section className="mb-10">
        <h2 className="mb-3 font-mono text-[0.9rem] tracking-[0.02em] text-accent">contents</h2>
        <BookToc chapters={refs} withRefs />
      </section>

      {bodies.map(({ slug, Body }) => {
        const chapter = chapters.find((c) => c.slug === slug);
        if (!chapter) return null;
        return (
          <section key={slug} className="book-chapter">
            {/* The anchor the front matter\'s page reference is resolved
                against. It is a marker, not a link target: the chapter\'s own
                headings carry the reader-visible anchors. */}
            <div data-book-anchor={`/book/${slug}/`} />
            <p className="m-0 font-mono text-[0.8rem] text-accent">
              {String(chapter.order).padStart(2, "0")}
            </p>
            <h1 className="mb-2 font-display text-[1.8rem] tracking-[-0.02em] text-ink">{chapter.title}</h1>
            <p className="mb-6 max-w-[64ch] text-ink-soft">{chapter.summary}</p>
            <Body />
          </section>
        );
      })}
    </div>
  );
}

export const dynamic = "force-static";
