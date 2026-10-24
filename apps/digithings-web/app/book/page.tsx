import Link from "next/link";

import BookDownloadButton from "@/components/book/BookDownloadButton";
import BookReader from "@/components/book/BookReader";
import { briefChapters } from "@/lib/book/brief";
import { chapterRefs, loadChapters } from "@/lib/book/chapters.server";
import type { ReaderPage } from "@/lib/book/reader";
import { WORDMARK } from "@/lib/book/wordmark";

const SHEET =
  "book-chapter mb-10 scroll-mt-[calc(var(--dq-nav-h)+1.5rem)] border border-hair px-[clamp(1.25rem,4vw,3rem)] py-[clamp(1.5rem,4vw,3rem)]";

/**
 * The book on screen reads like the PDF (lib/book/brief.ts): the same cover,
 * contents, chapters and closing page, in the same order, one sheet each.
 * Every chapter sheet links on to its full chapter, where the sections that
 * paper leaves out carry the depth.
 */
export default async function BookIndexPage() {
  const all = loadChapters(process.cwd());
  const chapters = briefChapters(all);
  // Numbered as printed, and linked to the sheets on this page.
  const refs = briefChapters(chapterRefs(all)).map((chapter, index) => ({
    ...chapter,
    order: index + 1,
    href: `#${chapter.slug}`,
  }));

  const bodies = await Promise.all(
    chapters.map(async (chapter) => ({
      chapter,
      Opener: (
        (await import(`../../content/book/${chapter.slug}/index.mdx`)) as {
          default: () => React.JSX.Element;
        }
      ).default,
    })),
  );

  const number = (index: number) => String(index + 1).padStart(2, "0");
  const pages: ReaderPage[] = [
    { id: "cover", number: "", title: "the digithings book" },
    { id: "contents", number: "", title: "contents" },
    ...chapters.map((chapter, index) => ({
      id: chapter.slug,
      number: number(index),
      title: chapter.title,
    })),
    { id: "end", number: "", title: "closing" },
  ];

  return (
    <BookReader pages={pages}>
      <section
        id="cover"
        tabIndex={-1}
        data-book-sheet
        aria-label="Cover"
        className={`${SHEET} text-center`}
      >
        <p className="m-0 font-mono text-[0.75rem] tracking-[0.12em] text-ink-soft">
          digithings · edition 2026 · version 1.0
        </p>
        <div
          className="mx-auto my-[clamp(2rem,6vw,4rem)] w-full max-w-[36rem]"
          aria-hidden
          dangerouslySetInnerHTML={{ __html: WORDMARK }}
        />
        <h1 className="m-0 font-display text-[clamp(1.9rem,3.6vw,2.6rem)] leading-[1.08] tracking-[-0.02em] text-ink">
          the digithings book
        </h1>
      </section>

      <section
        id="contents"
        tabIndex={-1}
        data-book-sheet
        aria-labelledby="contents-title"
        className={SHEET}
      >
        <h2
          id="contents-title"
          className="mt-0 mb-6 font-mono text-[0.8rem] tracking-[0.16em] text-accent"
        >
          contents
        </h2>
        {/* The printed contents: number and title, nothing else. */}
        <ol className="m-0 list-none p-0 font-mono text-[0.9rem]">
          {refs.map((chapter) => (
            <li key={chapter.slug} className="border-hair border-b last:border-b-0">
              <a
                href={chapter.href}
                className="flex min-h-11 items-baseline gap-3 py-2 text-ink-soft hover:text-ink"
              >
                <span className="w-6 shrink-0 text-accent">
                  {String(chapter.order).padStart(2, "0")}
                </span>
                <span>{chapter.title}</span>
              </a>
            </li>
          ))}
        </ol>
      </section>

      {bodies.map(({ chapter, Opener }, index) => (
        <section
          key={chapter.slug}
          id={chapter.slug}
          tabIndex={-1}
          data-book-sheet
          aria-labelledby={`${chapter.slug}-title`}
          className={SHEET}
        >
          <div className="mb-6 border-hair border-b pb-4">
            <p className="m-0 font-mono text-[0.8rem] text-accent">{number(index)}</p>
            <h2
              id={`${chapter.slug}-title`}
              className="mt-1 mb-0 font-display text-[clamp(1.6rem,3vw,2.1rem)] leading-[1.1] tracking-[-0.02em] text-ink"
            >
              {chapter.title}
            </h2>
          </div>
          <Opener />
          {chapter.sections.length > 0 ? (
            <p className="mt-8 mb-0 border-hair border-t pt-4 font-mono text-[0.8rem]">
              <Link href={chapter.href} className="text-accent hover:text-ink">
                the full chapter, with {chapter.sections.length} section
                {chapter.sections.length === 1 ? "" : "s"} →
              </Link>
            </p>
          ) : null}
        </section>
      ))}

      <section id="end" tabIndex={-1} data-book-sheet aria-label="Closing page" className={SHEET}>
        <div
          className="mx-auto w-full max-w-[34rem]"
          aria-hidden
          dangerouslySetInnerHTML={{ __html: WORDMARK }}
        />
        <div className="mt-10 border-hair border-t pt-4">
          <p className="m-0 font-mono text-[0.75rem] tracking-[0.16em] text-ink-soft">
            the digithings book
          </p>
          <p className="mt-2 mb-6 font-display text-[1.4rem] text-ink">
            edition 2026 · version 1.0
          </p>
          <p className="m-0 flex flex-wrap items-baseline gap-x-4 gap-y-2 font-mono text-[0.8rem]">
            <BookDownloadButton className="inline-flex min-h-11 items-center border-hair border-b text-accent hover:text-ink" />
            <Link href="/book/print/" className="text-accent hover:text-ink">
              printable edition
            </Link>
          </p>
        </div>
      </section>
    </BookReader>
  );
}
