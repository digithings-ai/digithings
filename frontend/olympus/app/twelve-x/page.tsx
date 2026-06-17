import { Suspense } from 'react';
import AtlasLoader from '@/components/AtlasLoader';
import TwelveXClient from '@/components/twelve-x/TwelveXClient';

/**
 * OLYMPUS FX Research suite (twelve-x). Thin server wrapper → Suspense →
 * client, mirroring `app/research/page.tsx`. Linked in the sidebar nav; the
 * client renders based on Supabase configuration (see `isTwelveXConfigured`).
 */
export default function TwelveXPage() {
  return (
    <Suspense fallback={<AtlasLoader />}>
      <TwelveXClient />
    </Suspense>
  );
}
