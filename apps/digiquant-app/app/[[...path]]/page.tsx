import { notFound, redirect } from 'next/navigation';
import { BookTable } from '@/components/BookTable';
import { Window } from '@/components/Window';
import { HOME, findPage } from '@/lib/nav';

/** A page is its slash-path. Pages without blocks yet show their path only. */
export default async function Page({ params }: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await params;
  if (path.length === 0) redirect(HOME);
  const full = '/' + path.join('/');
  const node = findPage(full);
  if (!node) notFound();

  if (full === '/portfolio/holdings') return <BookTable />;

  return (
    <Window no="00" label={node.label} right={full}>
      <p className="note mute">No blocks placed on this page yet.</p>
    </Window>
  );
}
