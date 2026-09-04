'use client';

import { useEffect, useState } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { PerformanceTearsheetView } from '@/components/tearsheet/DashboardTearsheetView';
import { EntitledSurface } from '@/components/entitled-surface';
import { fetchPerformanceTearsheet } from '@/lib/observability-queries';
import { useCan } from '@/lib/use-entitlement';
import type { PerformanceTearsheet } from '@/components/tearsheet/types';

/**
 * Tearsheet — persisted cumulative returns and stored holding-attribution
 * windows. The screen does not recalculate headline metrics from raw NAV.
 *
 * Tier: `house_weights_nav` (Baseline+). Skip the tearsheet fetch when locked
 * (fail-closed + saves quota).
 */
export default function PerformancePage() {
  const allowed = useCan('house_weights_nav');
  const [data, setData] = useState<PerformanceTearsheet | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!allowed) return;
    let alive = true;
    fetchPerformanceTearsheet()
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load performance data');
      });
    return () => {
      alive = false;
    };
  }, [allowed]);

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="tearsheet" />
      {/* No py-* utilities here: .ts-page owns the vertical padding. Under the
          old unlayered sheet they were dead declarations; against the family
          sheet's @layer components defaults they would win and shrink the
          shipped clamp() padding. */}
      <div className={`${SUBPAGE_MAX} ts-page flex-1`}>
        <EntitledSurface artifactClass="house_weights_nav">
          {error ? (
            <p className="ts-status ts-status-error">{error}</p>
          ) : !data ? (
            // bare: .ts-page already owns the container + padding (#1548)
            <PageSkeleton bare />
          ) : (
            <PerformanceTearsheetView data={data} />
          )}
        </EntitledSurface>
      </div>
    </div>
  );
}
