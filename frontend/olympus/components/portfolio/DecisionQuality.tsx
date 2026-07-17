'use client';

import { useEffect, useState } from 'react';
import { Skeleton, SkeletonGroup } from '@digithings/web';
import DecisionScorecardTab from '@/components/observability/DecisionScorecardTab';
import { fetchObservabilityData } from '@/lib/observability-queries';
import type { TableRow } from '@/lib/database.types';

/**
 * "Decision quality" — the conviction calibration scorecard, surfaced where the
 * owner asks "how am I doing" (Portfolio → Performance) rather than in the
 * operator System view. Reads resolved `decision_log` rows the same way the
 * System dashboard does. `decisions` may be injected (tests); otherwise it is
 * fetched on mount.
 */
export default function DecisionQuality({
  decisions: provided,
}: {
  decisions?: TableRow<'decision_log'>[];
}) {
  const [decisions, setDecisions] = useState<TableRow<'decision_log'>[] | null>(provided ?? null);
  const [loading, setLoading] = useState(provided == null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (provided != null) return;
    let alive = true;
    fetchObservabilityData()
      .then((d) => {
        if (alive) setDecisions(d.decisions);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load decisions');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [provided]);

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-1">
        <h2 className="font-display text-2xl tracking-tight text-ink">Decision quality</h2>
        <p className="text-sm text-ink-mute">
          Are high-conviction calls paying off? Realized alpha vs SPY by conviction bucket.
        </p>
      </div>
      {loading ? (
        // Scorecard-shaped skeleton (stat-tile row + chart block), not the
        // brand loader — the section heading above is already visible (#1548).
        <SkeletonGroup aria-label="Loading decision quality" className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} variant="block" className="h-20 w-full" />
            ))}
          </div>
          <Skeleton variant="block" className="h-64 w-full" />
        </SkeletonGroup>
      ) : error ? (
        <p className="text-sm text-down">{error}</p>
      ) : (
        <DecisionScorecardTab decisions={decisions ?? []} />
      )}
    </section>
  );
}
