import { Suspense } from 'react';
import WhyClient from '@/components/why/why-client';
import AtlasLoader from '@/components/AtlasLoader';

// Why — the reasoning surface: The read · Deliberations · Documents.
export default function WhyPage() {
  return (
    <Suspense fallback={<AtlasLoader />}>
      <WhyClient />
    </Suspense>
  );
}
