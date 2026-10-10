import type { Metadata } from "next";
import { notFound } from "next/navigation";

import ChapterNav from "@/components/book/ChapterNav";
import ChapterRail from "@/components/book/ChapterRail";
import { chapterRefs, loadChapter, loadChapters } from "@/lib/book/chapters.server";
import { join } from "node:path";

/** Every chapter is a static page: `output: "export"` has no server to ask. */
export function generateStaticParams(): Array<{ slug: string }> {
  return loadChapters(process.cwd()).map((c) => ({ slug: c.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const chapter = loadChapter(join(process.cwd(), "content/book", `${slug}.mdx`), `${slug}.mdx`);
  return { title: `${chapter.title} — the digithings book`, description: chapter.summary };
}

/**
 * One chapter (DIG-2821).
 *
 * The body is imported from `content/book/` through the MDX loader, not read
 * as text: the chapters are MDX, and the anchors come from the rehype plugin
 * (`lib/book/rehypeBookIds.mjs`), so the ids are in the static HTML the print
 * step paginates.
 */
export default async function ChapterPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const chapters = loadChapters(process.cwd());
  const chapter = chapters.find((c) => c.slug === slug);
  if (!chapter) notFound();

  // The static prefix keeps webpack's dynamic import a real context module, so
  // every chapter is bundled at build rather than fetched at request time.
  const { default: Body } = (await import(
    `../../../content/book/${slug}.mdx`
  )) as { default: () => React.JSX.Element };

  const refs = chapterRefs(chapters);
  return (
    <article className="book-chapter pt-[clamp(3rem,7vw,5rem)]">
      <p className="m-0 font-mono text-[0.8rem] text-accent">{String(chapter.order).padStart(2, "0")}</p>
      <h1 className="mb-2 font-display text-[clamp(2rem,4vw,3rem)] leading-[1.05] tracking-[-0.02em] text-ink">
        {chapter.title}
      </h1>
      <p className="max-w-[64ch] text-[1.05rem] leading-[1.7] text-ink-soft">{chapter.summary}</p>

      <div className="mt-10 grid gap-12 md:grid-cols-[minmax(0,1fr)_14rem]">
        <div className="min-w-0">
          <Body />
          <ChapterNav chapters={refs} slug={slug} />
        </div>
        <aside className="book-screen-only md:sticky md:top-[calc(var(--dq-nav-h)+2rem)] md:self-start">
          <ChapterRail entries={chapter.toc} />
        </aside>
      </div>
    </article>
  );
}
