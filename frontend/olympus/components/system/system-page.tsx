'use client';

import { useEffect, useState } from 'react';
import { Skeleton, SkeletonGroup } from '@digithings/web';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import { EmptyState } from '@/components/observability/shared';
import { fetchAtlasRunDiagnostics } from '@/lib/observability-queries';
import type { AtlasRunDiagnostics } from '@/lib/types';
import { FreshnessBanner, latestSuccessfulRun } from './freshness-banner';
import { RunEconomicsRow } from './run-economics-row';
import { RunHealthTimeline } from './run-health-timeline';
import { PerPhaseHealthStrip } from './per-phase-health-strip';
import { HowItWorks } from './how-it-works';

/** Zone 1 — live status. Pure in its props so it is unit-testable. */
export function SystemStatus({ diagnostics }: { diagnostics: AtlasRunDiagnostics[] }) {
  if (!diagnostics.length) {
    return (
      <EmptyState
        title="No runs recorded yet"
        message="The pipeline writes a diagnostics row at the end of each Atlas/Hermes run. Once a baseline or delta run completes, its status, cost, and segment health appear here."
      />
    );
  }
  return (
    <div className="flex flex-col gap-6">
      {(() => {
        const ok = latestSuccessfulRun(diagnostics);
        return ok ? (
          <FreshnessBanner latest={ok} />
        ) : (
          <div className="glass-card p-4 text-sm text-warn">
            No successful run yet — the most recent attempts did not complete. See the timeline below.
          </div>
        );
      })()}
      <RunEconomicsRow latest={diagnostics[0]} />
      <RunHealthTimeline diagnostics={diagnostics} />
      <PerPhaseHealthStrip latest={diagnostics[0]} />
    </div>
  );
}

export default function SystemPage() {
  const [diagnostics, setDiagnostics] = useState<AtlasRunDiagnostics[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    fetchAtlasRunDiagnostics()
      .then((d) => alive && setDiagnostics(d))
      .catch(() => alive && setDiagnostics([])) // fetch is fail-soft; treat a throw as empty
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className={`${SUBPAGE_MAX} space-y-8 py-4 md:py-6`}>
      <header className="space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-ink-mute">
          System
        </p>
        <h1 className="font-display text-3xl tracking-tight text-ink sm:text-4xl">
          How Olympus works
        </h1>
        <p className="max-w-3xl text-sm leading-relaxed text-ink-soft">
          Is it running, is it healthy, what does it cost, and how does it work?
        </p>
      </header>

      {loading ? (
        // Status-zone-shaped skeleton (banner + economics tiles + timeline),
        // not the brand loader — the page header above is already visible (#1548).
        <SkeletonGroup aria-label="Loading run diagnostics" className="flex flex-col gap-6">
          <Skeleton variant="block" className="h-14 w-full" />
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} variant="block" className="h-20 w-full" />
            ))}
          </div>
          <Skeleton variant="block" className="h-40 w-full" />
        </SkeletonGroup>
      ) : (
        <SystemStatus diagnostics={diagnostics ?? []} />
      )}

      <HowItWorks />
    </div>
  );
}
