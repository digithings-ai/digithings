import { notFound, redirect } from 'next/navigation';
import { BookBlock } from '@/components/blocks';
import { Gallery, GroupGallery, PortfolioGallery } from '@/components/Gallery';
import { GROUP_PAGES } from '@/lib/group-pages';
import { UiFixtures } from '@/components/UiFixtures';
import { Window } from '@/components/Window';
import { HOME, findPage } from '@/lib/nav';

/** A page is its slash-path. Pages without blocks yet show their path only. */
export default async function Page({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await params;
  if (path.length === 0) redirect(HOME);
  const full = '/' + path.join('/');
  if (full === '/blocks') return <Gallery />;
  if (full === '/blocks/ui') return <UiFixtures />;
  if (full === '/blocks/portfolio') return <PortfolioGallery />;
  const grp = full.startsWith('/blocks/') ? full.slice(8) : null;
  if (grp && grp in GROUP_PAGES) return <GroupGallery group={grp} />;
  const node = findPage(full);
  if (!node) notFound();

  if (full === '/portfolio/holdings') return <BookBlock />;

  return (
    <Window no="00" label={node.label} right={full}>
      <p className="note mute">No blocks placed on this page yet.</p>
    </Window>
  );
}
