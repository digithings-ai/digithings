'use client';

import { useEffect, useState } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { PerformanceTearsheetView } from '@/components/tearsheet/DashboardTearsheetView';
import { EntitledSurface } from '@/components/entitled-surface';
import { fetchPortfolioAttribution, getPerformanceBundle } from '@/lib/observability-queries';
import type { PerformanceSsotMeta } from '@/lib/performance-ssot';
import type { TableRow } from '@/lib/database.types';
import { useCan } from '@/lib/use-entitlement';
import type { PerformanceTearsheet } from '@/components/tearsheet/types';

/**
 * Performance: persisted cumulative returns, NAV vs benchmark, drawdown,
 * contribution and the current-book lookback bridge. Loads via
 * `getPerformanceBundle` (same NAV adapter as Brief #3580); the screen does not
 * recalculate headline metrics from raw NAV outside that shared builder. The
 * attribution fetch is fail-soft: without it the bridge shows its empty state.
 *
 * Tier: `house_weights_nav` (Baseline+). Skip fetches when locked
 * (fail-closed + saves quota).
 */
export default function PerformancePage() {
  const allowed = useCan('house_weights_nav');
  const [data, setData] = useState<PerformanceTearsheet | null>(null);
  const [ssot, setSsot] = useState<PerformanceSsotMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attribution, setAttribution] = useState<TableRow<'position_attribution'>[]>([]);

  useEffect(() => {
    if (!allowed) return;
    let alive = true;
    getPerformanceBundle()
      .then((bundle) => {
        if (alive) {
          setData(bundle.tearsheet);
          setSsot(bundle.ssot);
        }
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load performance data');
      });
    fetchPortfolioAttribution()
      .then((res) => {
        if (alive) setAttribution(res.attribution);
      })
      .catch(() => {
        /* fail-soft: bridge renders its empty state */
      });
    return () => {
      alive = false;
    };
  }, [allowed]);

  return (
    // No py-* utilities here: .ts-page owns the vertical padding (family sheet
    // @layer components defaults would lose to, or shrink, the shipped clamp()).
    <div className={`${SUBPAGE_MAX} ts-page flex-1`}>
      <EntitledSurface artifactClass="house_weights_nav">
        {error ? (
          <>
            <h1 className="sr-only">Performance</h1>
            <p className="ts-status ts-status-error">{error}</p>
          </>
        ) : !data ? (
          <>
            <h1 className="sr-only">Performance</h1>
            {/* bare: .ts-page already owns the container + padding (#1548) */}
            <PageSkeleton bare />
          </>
        ) : (
          <PerformanceTearsheetView data={data} ssot={ssot} attribution={attribution} />
        )}
      </EntitledSurface>
    </div>
  );
}
