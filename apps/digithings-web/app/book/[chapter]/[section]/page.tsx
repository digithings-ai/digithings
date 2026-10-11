import type { Metadata } from "next";
import { notFound } from "next/navigation";

import BookPage from "@/components/book/BookPage";
import { chapterRefs, loadChapters } from "@/lib/book/chapters.server";
import { sectionNeighbours } from "@/lib/book/toc";

/** One page per section: `/book/<chapter>/<section>/`. */
export function generateStaticParams(): Array<{ chapter: string; section: string }> {
  return loadChapters(process.cwd()).flatMap((c) => c.sections.map((s) => ({ chapter: c.slug, section: s.slug })));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ chapter: string; section: string }>;
}): Promise<Metadata> {
  const { chapter, section } = await params;
  const c = loadChapters(process.cwd()).find((x) => x.slug === chapter);
  const s = c?.sections.find((x) => x.slug === section);
  return s && c ? { title: `${s.title} — ${c.title} — the digithings book`, description: s.summary } : {};
}

export default async function SectionPage({ params }: { params: Promise<{ chapter: string; section: string }> }) {
  const { chapter: chapterSlug, section: sectionSlug } = await params;
  const chapters = loadChapters(process.cwd());
  const chapter = chapters.find((c) => c.slug === chapterSlug);
  const section = chapter?.sections.find((s) => s.slug === sectionSlug);
  if (!chapter || !section) notFound();

  // Static prefix: webpack bundles every section as a context module at build.
  const { default: Body } = (await import(`../../../../content/book/${chapterSlug}/${sectionSlug}.mdx`)) as {
    default: () => React.JSX.Element;
  };
  const refs = chapterRefs(chapters);
  const { previous, next } = sectionNeighbours(refs, chapterSlug, sectionSlug);

  return (
    <BookPage
      chapters={refs}
      chapter={chapterSlug}
      section={sectionSlug}
      kicker={`${String(chapter.order).padStart(2, "0")}.${section.order} · ${chapter.title}`}
      title={section.title}
      summary={section.summary}
      toc={section.toc}
      previous={previous}
      next={next}
    >
      <Body />
    </BookPage>
  );
}
