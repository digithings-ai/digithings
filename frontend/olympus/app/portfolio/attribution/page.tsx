'use client';

import { useEffect, useState } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import AttributionWorkspace from '@/components/portfolio/AttributionWorkspace';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import HouseIdentityBanner from '@/components/house/HouseIdentityBanner';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import {
  fetchPortfolioAttribution,
  type PortfolioAttributionData,
} from '@/lib/observability-queries';

export default function AttributionPage() {
  const [data, setData] = useState<PortfolioAttributionData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchPortfolioAttribution()
      .then((result) => {
        if (alive) setData(result);
      })
      .catch((cause: unknown) => {
        if (alive) {
          setError(cause instanceof Error ? cause.message : 'Failed to load attribution data');
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex min-h-full flex-col">
      <HouseIdentityBanner />
      <PortfolioSectionNav active="attribution" />
      <main className={`${SUBPAGE_MAX} flex-1 py-4 md:py-5`}>
        <h1 className="sr-only">Attribution</h1>
        {error ? (
          <p className="text-sm text-down">{error}</p>
        ) : !data ? (
          <PageSkeleton bare />
        ) : (
          <AttributionWorkspace
            attribution={data.attribution}
            attributionDate={data.attributionDate}
            decisions={data.decisions}
          />
        )}
      </main>
    </div>
  );
}