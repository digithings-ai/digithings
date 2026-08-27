'use client';

import HouseIdentityBanner from '@/components/house/HouseIdentityBanner';
import PeriodInspectPanel from '@/components/portfolio/PeriodInspectPanel';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import { SUBPAGE_MAX } from '@/components/layout-constants';

export default function PortfolioPeriodPage() {
  return (
    <div className="flex min-h-full flex-col">
      <HouseIdentityBanner />
      <PortfolioSectionNav active="period" />
      <div className={`${SUBPAGE_MAX} flex-1 py-4 md:py-5`}>
        <PeriodInspectPanel />
      </div>
    </div>
  );
}
