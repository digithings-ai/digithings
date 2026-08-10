import { Suspense } from 'react';
import PortfolioShellInner from '@/components/portfolio/PortfolioShellInner';
import PageSkeleton from '@/components/page-skeleton';

export default function PortfolioPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <PortfolioShellInner />
    </Suspense>
  );
}
