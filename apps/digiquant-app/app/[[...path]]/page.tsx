import { redirect } from 'next/navigation';
import { AtomsGallery } from '@/components/AtomsGallery';
import { BlockGrid } from '@/components/BlockGrid';
import { Gallery, GroupGallery, PortfolioGallery } from '@/components/Gallery';
import { GROUP_PAGES } from '@/lib/group-pages';
import { UiFixtures } from '@/components/UiFixtures';
import { Window } from '@/components/Window';
import { HOME } from '@/lib/nav';
import { PAGE_LAYOUTS } from '@/lib/pages';

/** A page is its slash-path. Pages without blocks yet show their path only. */
export default async function Page({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await params;
  if (path.length === 0) redirect(HOME);
  const full = '/' + path.join('/');
  if (full === '/blocks') return <Gallery />;
  if (full === '/blocks/ui') return <UiFixtures />;
  if (full === '/blocks/atoms') return <AtomsGallery />;
  if (full === '/blocks/portfolio') return <PortfolioGallery />;
  const grp = full.startsWith('/blocks/') ? full.slice(8) : null;
  if (grp && grp in GROUP_PAGES) return <GroupGallery group={grp} />;
  const layout = PAGE_LAYOUTS[full];
  if (layout) return <BlockGrid pageId={full} initial={layout} />;

  return (
    <Window no="00" label={full.split('/').pop() ?? full} right={full}>
      <p className="note mute">No blocks placed on this page yet.</p>
    </Window>
  );
}
