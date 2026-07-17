import { Suspense } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import TwelveXClient from '@/components/twelve-x/TwelveXClient';

/**
 * OLYMPUS FX Research suite (twelve-x). Thin server wrapper → Suspense →
 * client, mirroring `app/research/page.tsx`. Linked in the sidebar nav; the
 * client renders based on Supabase configuration (see `isTwelveXConfigured`).
 */
export default function TwelveXPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <TwelveXClient />
    </Suspense>
  );
}
