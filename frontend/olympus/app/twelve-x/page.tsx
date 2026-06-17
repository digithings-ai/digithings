import { Suspense } from 'react';
import AtlasLoader from '@/components/AtlasLoader';
import TwelveXClient from '@/components/twelve-x/TwelveXClient';

/**
 * OLYMPUS FX Research suite (twelve-x). Thin server wrapper → Suspense →
 * client, mirroring `app/research/page.tsx`. The route is intentionally
 * UNLINKED from the sidebar nav (gated behind NEXT_PUBLIC_TWELVEX_ENABLED).
 */
export default function TwelveXPage() {
  return (
    <Suspense fallback={<AtlasLoader />}>
      <TwelveXClient />
    </Suspense>
  );
}
