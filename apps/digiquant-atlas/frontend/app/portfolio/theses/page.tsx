import { Suspense } from 'react';
import ThesesPageInner from '@/components/portfolio/theses/ThesesPageInner';
import AtlasLoader from '@/components/AtlasLoader';

export default function PortfolioThesesPage() {
  return (
    <Suspense fallback={<AtlasLoader />}>
      <ThesesPageInner />
    </Suspense>
  );
}
