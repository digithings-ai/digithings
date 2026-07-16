import { Suspense } from 'react';
import WhyClient from '@/components/why/why-client';
import PageSkeleton from '@/components/page-skeleton';

// Why — the reasoning surface: The read · Deliberations · Documents.
// Fallback is a content-shaped skeleton, not the AtlasLoader brand moment,
// per the #1548 ruling (brand loader stays at app boot only).
export default function WhyPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <WhyClient />
    </Suspense>
  );
}
