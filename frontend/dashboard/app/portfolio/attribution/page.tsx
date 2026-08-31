'use client';

import { useEffect, useState } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import AttributionWorkspace from '@/components/portfolio/AttributionWorkspace';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { EntitledSurface } from '@/components/entitled-surface';
import {
  fetchPortfolioAttribution,
  type PortfolioAttributionData,
} from '@/lib/observability-queries';
import { useCan } from '@/lib/use-entitlement';

/**
 * Attribution workspace — Decision effectiveness / Book attribution / Audit.
 * Tier: `house_weights_nav` (Baseline+). Skip the attribution fetch when locked.
 */
export default function AttributionPage() {
  const allowed = useCan('house_weights_nav');
  const [data, setData] = useState<PortfolioAttributionData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!allowed) return;
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
  }, [allowed]);

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="attribution" />
      <main className={`${SUBPAGE_MAX} flex-1 py-4 md:py-5`}>
        <h1 className="sr-only">Attribution</h1>
        <EntitledSurface artifactClass="house_weights_nav">
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
        </EntitledSurface>
      </main>
    </div>
  );
}
