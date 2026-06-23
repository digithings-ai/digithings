'use client';

import { useEffect, useState } from 'react';
import AtlasLoader from '@/components/AtlasLoader';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import AttributionTab from '@/components/observability/AttributionTab';
import PositionRiskTab from '@/components/observability/PositionRiskTab';
import RunHealthTab from '@/components/observability/RunHealthTab';
import { EmptyState } from '@/components/observability/shared';
import { fetchObservabilityData, type ObservabilityData } from '@/lib/observability-queries';
import { HowOlympusWorks } from '@/components/system/how-olympus-works';

/**
 * System — the demoted operator footnote. Primary content is Run health and the
 * "How Olympus works" explainer; deeper operator diagnostics (attribution,
 * per-position risk) live behind a collapsed disclosure so they never compete
 * with the owner-facing surfaces. The conviction scorecard moved to
 * Portfolio → Performance, so it is intentionally not shown here.
 */
export default function SystemPage() {
  const [data, setData] = useState<ObservabilityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchObservabilityData()
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load system data');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className={`${SUBPAGE_MAX} flex-1 space-y-10 py-4 md:py-6`}>
      <header className="flex flex-col gap-1">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">System</p>
        <h1 className="text-lg font-semibold text-text-primary">System</h1>
        <p className="text-sm text-text-muted">
          Pipeline health and how Olympus works — the operator&rsquo;s view, kept out of the way.
        </p>
      </header>

      {/* Run health — the one thing an owner might glance at here. */}
      <section className="space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-widest text-text-muted">Run health</h2>
        {loading ? (
          <AtlasLoader fullScreen={false} />
        ) : error || !data ? (
          <EmptyState
            title="Couldn't load run health"
            message={error ?? 'No data is available right now. Try again shortly.'}
          />
        ) : (
          <RunHealthTab runHealth={data.runHealth} available={data.runHealthAvailable} />
        )}
      </section>

      {/* Diagnostics — operator-only depth, collapsed and quiet. */}
      <details className="glass-card overflow-hidden">
        <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-3.5 text-sm font-medium text-text-secondary transition-colors hover:text-text-primary">
          <span>Diagnostics</span>
          <span className="text-[11px] text-text-muted">attribution · position risk</span>
        </summary>
        <div className="space-y-8 border-t border-border-subtle p-5">
          {loading ? (
            <AtlasLoader fullScreen={false} />
          ) : error || !data ? (
            <p className="text-sm text-text-muted">Diagnostics unavailable right now.</p>
          ) : (
            <>
              <AttributionTab attribution={data.attribution} date={data.attributionDate} />
              <PositionRiskTab positions={data.positions} date={data.positionsDate} />
            </>
          )}
        </div>
      </details>

      {/* How Olympus works — the pipeline explainer (formerly /architecture). */}
      <section>
        <HowOlympusWorks />
      </section>
    </div>
  );
}
