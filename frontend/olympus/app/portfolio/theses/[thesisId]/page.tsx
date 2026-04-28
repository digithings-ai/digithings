import { Suspense } from 'react';
import ThesisDetailClient from './thesis-detail-client';
import AtlasLoader from '@/components/AtlasLoader';
import { THESIS_BUILD_STATIC_PARAMS } from '@/lib/thesis-static-params';

/** Required for `output: 'export'` — extend `THESIS_BUILD_STATIC_PARAMS` for production thesis slugs. */
export function generateStaticParams() {
  return THESIS_BUILD_STATIC_PARAMS;
}

export default function PortfolioThesisDetailPage() {
  return (
    <Suspense fallback={<AtlasLoader />}>
      <ThesisDetailClient />
    </Suspense>
  );
}
