import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import BookPage from "@/components/book/BookPage";
import { chapterRefs, loadChapters } from "@/lib/book/chapters.server";
import { readingOrder } from "@/lib/book/toc";

/** Every chapter opener is a static page: `output: "export"` has no server. */
export function generateStaticParams(): Array<{ chapter: string }> {
  return loadChapters(process.cwd()).map((c) => ({ chapter: c.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ chapter: string }> }): Promise<Metadata> {
  const { chapter } = await params;
  const c = loadChapters(process.cwd()).find((x) => x.slug === chapter);
  return c ? { title: `${c.title} — the digithings book`, description: c.summary } : {};
}

/**
 * A chapter's opener (DIG-2821): its introduction and the list of its sections.
 * Each section is its own page; "next" goes to the first of them.
 */
export default async function ChapterPage({ params }: { params: Promise<{ chapter: string }> }) {
  const { chapter: slug } = await params;
  const chapters = loadChapters(process.cwd());
  const chapter = chapters.find((c) => c.slug === slug);
  if (!chapter) notFound();

  const { default: Body } = (await import(`../../../content/book/${slug}/index.mdx`)) as {
    default: () => React.JSX.Element;
  };
  const refs = chapterRefs(chapters);
  const flat = readingOrder(refs);
  const first = flat.findIndex((s) => s.chapter === slug);
  const previous = first > 0 ? flat[first - 1] : null;

  return (
    <BookPage
      chapters={refs}
      chapter={slug}
      kicker={`chapter ${String(chapter.order).padStart(2, "0")}`}
      title={chapter.title}
      summary={chapter.summary}
      toc={chapter.toc}
      previous={previous}
      next={first >= 0 ? flat[first] : null}
    >
      <Body />
      <ol className="mt-8 list-none border-hair border-t p-0">
        {chapter.sections.map((s) => (
          <li key={s.slug} className="border-hair border-b py-3">
            <Link href={s.href} className="font-mono text-[0.9rem] text-ink">
              {String(chapter.order).padStart(2, "0")}.{s.order} {s.title}
            </Link>
            <p className="m-0 mt-1 max-w-[64ch] text-ink-soft">{s.summary}</p>
          </li>
        ))}
      </ol>
    </BookPage>
  );
}
