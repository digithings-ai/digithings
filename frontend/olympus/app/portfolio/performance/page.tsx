'use client';

import { useEffect, useState } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { OlympusTearsheetView } from '@/components/tearsheet/OlympusTearsheetView';
import { fetchOlympusTearsheet } from '@/lib/observability-queries';
import type { OlympusTearsheet } from '@/components/tearsheet/types';

/**
 * Performance — persisted cumulative returns and stored holding-attribution
 * windows. The screen does not recalculate headline metrics from raw NAV.
 */
export default function PerformancePage() {
  const [data, setData] = useState<OlympusTearsheet | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchOlympusTearsheet()
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load performance data');
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="performance" />
      {/* No py-* utilities here: .ts-page owns the vertical padding. Under the
          old unlayered sheet they were dead declarations; against the family
          sheet's @layer components defaults they would win and shrink the
          shipped clamp() padding. */}
      <div className={`${SUBPAGE_MAX} ts-page flex-1`}>
        {error ? (
          <p className="ts-status ts-status-error">{error}</p>
        ) : !data ? (
          // bare: .ts-page already owns the container + padding (#1548)
          <PageSkeleton bare />
        ) : (
          <OlympusTearsheetView data={data} />
        )}
      </div>
    </div>
  );
}
