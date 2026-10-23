import type { Metadata } from "next";

import { sampleBanner, type Frame } from "@digithings/hero-banner";
import { DIGITHINGS } from "@digithings/hero-banner/definitions";

import BookToc from "@/components/book/BookToc";
import PagedBoot from "@/components/book/PagedBoot";
import { chapterRefs, loadChapters } from "@/lib/book/chapters.server";

/** An actual build-animation frame, as a print-safe SVG. */
function frameSvg(frame: Frame): string {
  const runs: string[] = [];
  for (let y = 0; y < frame.height; y += 1) {
    let x = 0;
    while (x < frame.width) {
      const pixel = frame.pixels[y * frame.width + x];
      if (!pixel || pixel.alpha <= 0) {
        x += 1;
        continue;
      }
      const tone = pixel.tone === "accent" ? "--accent" : "--ink";
      const alpha = Math.min(1, pixel.alpha);
      let width = 1;
      while (x + width < frame.width) {
        const next = frame.pixels[y * frame.width + x + width];
        if (!next || next.tone !== pixel.tone || Math.min(1, next.alpha) !== alpha) break;
        width += 1;
      }
      runs.push(
        `<rect x="${x}" y="${y}" width="${width}" height="1" fill="var(${tone})" fill-opacity="${alpha.toFixed(2)}"/>`,
      );
      x += width;
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${frame.width} ${frame.height}" preserveAspectRatio="xMidYMid meet" shape-rendering="crispEdges" aria-hidden="true">${runs.join("")}</svg>`;
}

/** Mid-build and near-settled frames from the same script the landing hero runs. */
const WORDMARK = frameSvg(sampleBanner(DIGITHINGS, { t: 940 }).frame);
const MOTION = frameSvg(sampleBanner(DIGITHINGS, { t: 1240 }).frame);

/**
 * The print artefact is a rendering of the same book content with PagedJS
 * chrome; it is not a destination page. Keep it out of the index (searchers
 * want /book, which is where we send them instead).
 */
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

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
    <div data-paged-content="book" className="book-flow mx-auto w-full max-w-[var(--wrap)] px-[var(--gutter)]">
      <PagedBoot enabled />

      <div className="book-print-only running-element">
        <span>the digithings book</span>
        <span>digithings.ai/book</span>
      </div>

      <section className="book-cover">
        <div className="book-cover__motion" aria-hidden dangerouslySetInnerHTML={{ __html: MOTION }} />
        <div className="book-cover__mark" aria-hidden dangerouslySetInnerHTML={{ __html: WORDMARK }} />
        <h1 className="book-cover__title">the digithings book</h1>
        <p className="book-cover__subtitle">
          A short, philosophical book about self-hosted AI infrastructure — why it matters, how it
          scales, and what it costs.
        </p>
        <p className="book-cover__meta">digithings.ai/book · edition 2026</p>
      </section>

      {/* Front matter. The reference beside each chapter is filled in by
          PagedBoot, after the engine has decided where the pages break — a
          number written here would be wrong the moment a paragraph grew a
          line. */}
      <section className="book-contents">
        <h2 className="book-contents__title">contents</h2>
        <BookToc chapters={refs} withRefs />
      </section>

      {bodies.map(({ chapter, Opener, sections }) => (
        <section key={chapter.slug} className="book-chapter">
          {/* Anchors the front matter's page references resolve against. */}
          <div data-book-anchor={chapter.href} />
          <div className="book-chapter__head">
            <p className="m-0 font-mono text-[0.8rem] text-accent">{String(chapter.order).padStart(2, "0")}</p>
            {/* The book title above is the page's single h1; chapter openers
                sit one level below it so the printed outline stays in order. */}
            <h2 className="mb-2 font-display text-[1.8rem] tracking-[-0.02em] text-ink">{chapter.title}</h2>
            <p className="mb-6 text-ink-soft">{chapter.summary}</p>
          </div>
          <Opener />
          {sections.map(({ section, Body }) => (
            <div key={section.slug} className="book-section">
              <div data-book-anchor={section.href} />
              <h3 className="mt-12 mb-4 font-display text-[1.6rem] leading-[1.15] tracking-[-0.01em] text-ink">
                {String(chapter.order).padStart(2, "0")}.{section.order} {section.title}
              </h3>
              <Body />
            </div>
          ))}
        </section>
      ))}

      <section className="book-colophon">
        <p className="book-colophon__kicker">colophon</p>
        <p className="book-colophon__title">the digithings book</p>
        <p>
          Set in the digithings mono voice. Built from the same files as the web edition at
          digithings.ai/book.
        </p>
        <p>Edition 2026 · digithings.ai</p>
        <p className="book-colophon__mark" aria-hidden="true">
          digithings
        </p>
      </section>
    </div>
  );
}

export const dynamic = "force-static";
