import { Suspense } from 'react';
import PortfolioShellInner from '@/components/portfolio/PortfolioShellInner';
import AtlasLoader from '@/components/AtlasLoader';

export default function PortfolioPage() {
  return (
    <Suspense
      fallback={
        <AtlasLoader />
      }
    >
      <PortfolioShellInner />
    </Suspense>
  );
}
