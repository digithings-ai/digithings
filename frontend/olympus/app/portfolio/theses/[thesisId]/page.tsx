import { Suspense } from 'react';
import ThesisDetailClient from './thesis-detail-client';
import AtlasLoader from '@/components/AtlasLoader';
import { fetchThesisStaticParams } from '@/lib/thesis-static-params';

/** Required for `output: 'export'` — resolves real thesis ids from Supabase at build time. */
export async function generateStaticParams() {
  return fetchThesisStaticParams();
}

export default function PortfolioThesisDetailPage() {
  return (
    <Suspense fallback={<AtlasLoader />}>
      <ThesisDetailClient />
    </Suspense>
  );
}
