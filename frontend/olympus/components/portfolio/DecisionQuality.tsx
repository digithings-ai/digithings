'use client';

import { useEffect, useState } from 'react';
import DecisionScorecardTab from '@/components/observability/DecisionScorecardTab';
import { fetchObservabilityData } from '@/lib/observability-queries';
import type { TableRow } from '@/lib/database.types';
import AtlasLoader from '@/components/AtlasLoader';

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
        <h2 className="font-display text-2xl tracking-tight text-text-primary">Decision quality</h2>
        <p className="text-sm text-text-muted">
          Are high-conviction calls paying off? Realized alpha vs SPY by conviction bucket.
        </p>
      </div>
      {loading ? (
        <AtlasLoader fullScreen={false} />
      ) : error ? (
        <p className="text-sm text-fin-red">{error}</p>
      ) : (
        <DecisionScorecardTab decisions={decisions ?? []} />
      )}
    </section>
  );
}
