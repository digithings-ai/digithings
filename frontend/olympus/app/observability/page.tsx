'use client';

import { useEffect, useState } from 'react';
import { Activity, BarChart3, ShieldAlert, Target } from 'lucide-react';
import AtlasLoader from '@/components/AtlasLoader';
import { SUBPAGE_MAX, SubpageStickyTabBar, subpageTabButtonClass } from '@/components/subpage-tab-bar';
import AttributionTab from '@/components/observability/AttributionTab';
import DecisionScorecardTab from '@/components/observability/DecisionScorecardTab';
import PositionRiskTab from '@/components/observability/PositionRiskTab';
import RunHealthTab from '@/components/observability/RunHealthTab';
import { EmptyState } from '@/components/observability/shared';
import { fetchObservabilityData, type ObservabilityData } from '@/lib/observability-queries';

type ObservabilityTab = 'scorecard' | 'health' | 'attribution' | 'risk';

const TABS: { id: ObservabilityTab; label: string; icon: typeof Target }[] = [
  { id: 'scorecard', label: 'Decision Scorecard', icon: Target },
  { id: 'attribution', label: 'Attribution', icon: BarChart3 },
  { id: 'risk', label: 'Position Risk', icon: ShieldAlert },
  { id: 'health', label: 'Run Health', icon: Activity },
];

export default function ObservabilityPage() {
  const [data, setData] = useState<ObservabilityData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ObservabilityTab>('scorecard');

  useEffect(() => {
    let alive = true;
    fetchObservabilityData()
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : 'Failed to load observability data');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="flex min-h-full flex-col">
      <SubpageStickyTabBar aria-label="Observability sections">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
            className={subpageTabButtonClass(activeTab === id)}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </SubpageStickyTabBar>

      <div className={`${SUBPAGE_MAX} flex-1 space-y-6 py-4 md:py-6`}>
        <div className="flex flex-col gap-1">
          <h1 className="text-lg font-semibold text-text-primary">Observability</h1>
          <p className="text-sm text-text-muted">
            Does the agent make money, and is it well-calibrated? Decision track record, performance
            attribution, per-position risk, and pipeline health.
          </p>
        </div>

        {loading ? (
          <AtlasLoader fullScreen={false} />
        ) : error || !data ? (
          <EmptyState
            title="Couldn't load observability data"
            message={error ?? 'No data is available right now. Try again shortly.'}
          />
        ) : (
          <>
            {activeTab === 'scorecard' && <DecisionScorecardTab decisions={data.decisions} />}
            {activeTab === 'attribution' && (
              <AttributionTab attribution={data.attribution} date={data.attributionDate} />
            )}
            {activeTab === 'risk' && (
              <PositionRiskTab positions={data.positions} date={data.positionsDate} />
            )}
            {activeTab === 'health' && (
              <RunHealthTab runHealth={data.runHealth} available={data.runHealthAvailable} />
            )}
          </>
        )}
      </div>
    </div>
  );
}
