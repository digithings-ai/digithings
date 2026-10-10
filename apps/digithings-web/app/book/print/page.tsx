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

  // Loaded up front, before any JSX: a page that will not compile must fail
  // the build, not leave a hole in the printed book. Every chapter opener and
  // every section, in reading order — the web splits them into pages, paper
  // flows them continuously.
  const bodies = await Promise.all(
    chapters.map(async (chapter) => {
      const load = async (file: string) =>
        ((await import(`../../../content/book/${chapter.slug}/${file}.mdx`)) as { default: () => React.JSX.Element })
          .default;
      return {
        chapter,
        Opener: await load("index"),
        sections: await Promise.all(chapter.sections.map(async (s) => ({ section: s, Body: await load(s.slug) }))),
      };
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

      {bodies.map(({ chapter, Opener, sections }) => (
        <section key={chapter.slug} className="book-chapter">
          {/* Anchors the front matter's page references resolve against. */}
          <div data-book-anchor={chapter.href} />
          <p className="m-0 font-mono text-[0.8rem] text-accent">{String(chapter.order).padStart(2, "0")}</p>
          <h1 className="mb-2 font-display text-[1.8rem] tracking-[-0.02em] text-ink">{chapter.title}</h1>
          <p className="mb-6 max-w-[64ch] text-ink-soft">{chapter.summary}</p>
          <Opener />
          {sections.map(({ section, Body }) => (
            <div key={section.slug} className="book-section">
              <div data-book-anchor={section.href} />
              <h2 className="mt-12 mb-4 font-display text-[1.6rem] leading-[1.15] tracking-[-0.01em] text-ink">
                {String(chapter.order).padStart(2, "0")}.{section.order} {section.title}
              </h2>
              <Body />
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}

export const dynamic = "force-static";
