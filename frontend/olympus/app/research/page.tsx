import { Suspense } from 'react';
import ResearchClient from './ResearchClient';
import AtlasLoader from '@/components/AtlasLoader';

export default function ResearchPage() {
  return (
    <Suspense fallback={<AtlasLoader />}>
      <ResearchClient />
    </Suspense>
  );
}
