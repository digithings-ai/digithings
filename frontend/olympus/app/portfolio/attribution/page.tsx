'use client';

import { useEffect, useState } from 'react';
import AttributionTab from '@/components/observability/AttributionTab';
import PageSkeleton from '@/components/page-skeleton';
import DecisionQuality from '@/components/portfolio/DecisionQuality';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
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
      <PortfolioSectionNav active="attribution" />
      <main className={`${SUBPAGE_MAX} flex-1 space-y-10 py-8 md:py-10`}>
        <header className="max-w-3xl space-y-2">
          <p className="font-mono text-xs uppercase text-ink-mute">Portfolio intelligence</p>
          <h1 className="font-display text-3xl text-ink md:text-4xl">Attribution</h1>
          <p className="text-sm leading-relaxed text-ink-mute md:text-base">
            Decompose the latest stored return window by position, then audit recommendation
            outcomes and conviction calibration.
          </p>
        </header>

        {error ? (
          <p className="text-sm text-down">{error}</p>
        ) : !data ? (
          <PageSkeleton bare />
        ) : (
          <div className="space-y-12">
            <section aria-labelledby="position-attribution-heading" className="space-y-4">
              <div className="space-y-1">
                <h2
                  id="position-attribution-heading"
                  className="font-display text-2xl text-ink"
                >
                  Position attribution
                </h2>
                <p className="text-sm text-ink-mute">
                  Contribution and active-return decomposition for the latest rolling window.
                </p>
              </div>
              <AttributionTab
                attribution={data.attribution}
                date={data.attributionDate}
              />
            </section>

            <DecisionQuality decisions={data.decisions} />
          </div>
        )}
      </main>
    </div>
  );
}