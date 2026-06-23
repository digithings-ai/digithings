import { Suspense } from 'react';
import ResearchClient from '../research/ResearchClient';
import AtlasLoader from '@/components/AtlasLoader';

// Phase 1: `/why` hosts the existing research client unchanged; the three-tab
// reasoning reorganization (The read / Deliberations / Documents) lands in Phase 4.
export default function WhyPage() {
  return (
    <Suspense fallback={<AtlasLoader />}>
      <ResearchClient />
    </Suspense>
  );
}
