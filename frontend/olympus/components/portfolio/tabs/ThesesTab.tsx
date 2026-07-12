'use client';

import { useMemo } from 'react';
import { useDashboard } from '@/lib/dashboard-context';
import { MarketViewCard } from '@/components/portfolio/theses/MarketViewCard';
import { VehicleThesisRow } from '@/components/portfolio/theses/VehicleThesisRow';
import { splitTheses, sortByConfidenceDesc, groupVehicleTheses } from '@/lib/theses-ledger';
import { aggregateWeightByThesis, bookWeightForThesis } from '@/lib/portfolio-aggregates';

function thesisHref(id: string): string {
  return `/portfolio/theses/${encodeURIComponent(id)}`;
}

/**
 * Two-tier theses ledger (the Portfolio "Theses" tab):
 * Market views (conviction cards, confidence desc) over Vehicle theses grouped
 * by their linked market view, with a trailing "Unlinked expressions" group.
 * Mounted inside PortfolioShellInner, which supplies the section nav + chrome.
 */
export default function ThesesTab() {
  const { data } = useDashboard();
  const lastUpdated = data?.portfolio?.meta?.last_updated ?? null;

  const theses = useMemo(() => data?.portfolio?.strategy?.theses ?? [], [data]);
  const positions = useMemo(() => data?.positions ?? [], [data]);
  const trackingSince = useMemo(() => {
    const dates = (data?.position_history ?? []).map((r) => r.date).filter(Boolean).sort();
    return dates[0] ?? data?.portfolio?.meta?.last_updated ?? null;
  }, [data]);

  const weightByThesisId = useMemo(
    () =>
      aggregateWeightByThesis(
        positions.map((p) => ({ weight_actual: p.weight_actual, thesis_ids: p.thesis_ids }))
      ),
    [positions]
  );

  const { market, vehicle } = useMemo(() => splitTheses(theses), [theses]);
  const marketSorted = useMemo(() => sortByConfidenceDesc(market), [market]);
  const vehicleGroups = useMemo(() => groupVehicleTheses(vehicle, market), [vehicle, market]);

  return (
    <div className="space-y-12">
      {/* Market views */}
      <section className="space-y-4">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-display text-2xl text-ink">Market views</h2>
          <p className="text-xs text-ink-mute">
            Ordered by conviction
            {lastUpdated ? <span className="font-mono"> · as of {lastUpdated}</span> : null}
          </p>
        </div>
        {marketSorted.length === 0 ? (
          <div className="glass-card p-6 text-sm text-ink-mute">
            No market views recorded yet.
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {marketSorted.map((t) => (
              <MarketViewCard
                key={t.id}
                thesis={t}
                bookWeightPct={bookWeightForThesis(t, weightByThesisId, theses)}
                href={thesisHref(t.id)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Vehicle theses */}
      <section className="space-y-4">
        <h2 className="font-display text-2xl text-ink">Vehicle theses</h2>
        {vehicleGroups.length === 0 ? (
          <div className="glass-card p-6 text-sm text-ink-mute">
            No single-name theses recorded yet.
          </div>
        ) : (
          <div className="space-y-6">
            {vehicleGroups.map((group) => (
              <div key={group.marketId ?? '_unlinked'} className="space-y-2">
                <div className="flex items-baseline gap-2 px-1">
                  <h3 className="text-sm font-semibold text-ink-soft">
                    {group.marketName ?? 'Unlinked expressions'}
                  </h3>
                  {group.marketId === null ? (
                    <span className="text-xs text-ink-mute">not yet tied to a market view</span>
                  ) : (
                    <span className="text-xs text-ink-mute">expresses this view</span>
                  )}
                </div>
                <div className="glass-card divide-y divide-hair overflow-hidden p-0">
                  {group.theses.map((t) => (
                    <VehicleThesisRow
                      key={t.id}
                      thesis={t}
                      bookWeightPct={bookWeightForThesis(t, weightByThesisId, theses)}
                      href={thesisHref(t.id)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* History — one quiet line on single-day data */}
      {trackingSince ? (
        <p className="text-xs text-ink-mute">
          Tracking theses from <span className="font-mono">{trackingSince}</span>.
        </p>
      ) : null}
    </div>
  );
}
