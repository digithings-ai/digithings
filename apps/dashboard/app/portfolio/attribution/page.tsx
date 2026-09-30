'use client';

import { useEffect, useState } from 'react';
import PageSkeleton from '@/components/page-skeleton';
import DecisionsView from '@/components/portfolio/DecisionsView';
import type { DecisionsPaneId } from '@/lib/portfolio-url-state';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { EntitledSurface } from '@/components/entitled-surface';
import {
  fetchPortfolioAttribution,
  type PortfolioAttributionData,
} from '@/lib/observability-queries';
import { useCan } from '@/lib/use-entitlement';

/**
 * Attribution route — renders the Decisions view (edge / audit) in place; book-level
 * attribution now lives on Performance. No theses pane here (see /portfolio?tab=decisions).
 * Tier: `house_weights_nav` (Baseline+). Skip the attribution fetch when locked.
 */
export default function AttributionPage() {
  const allowed = useCan('house_weights_nav');
  const [data, setData] = useState<PortfolioAttributionData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pane, setPane] = useState<DecisionsPaneId>('edge');

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
      <main className={`${SUBPAGE_MAX} flex-1 py-4 md:py-5`}>
        <h1 className="sr-only">Attribution</h1>
        <EntitledSurface artifactClass="house_weights_nav">
          {error ? (
            <p className="text-sm text-warn">{error}</p>
          ) : !data ? (
            <PageSkeleton bare />
          ) : (
            <DecisionsView decisions={data.decisions} pane={pane} onPaneChange={setPane} />
          )}
        </EntitledSurface>
      </main>
    </div>
  );
}
