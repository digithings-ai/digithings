'use client';

import { type KeyboardEvent, useState } from 'react';
import Link from 'next/link';
import { Newspaper } from 'lucide-react';
import {
  ActionableList,
  NarrativeSection,
  RiskList,
  SnapshotEmptyBanner,
  SnapshotErrorBanner,
  SnapshotSkeleton,
  useLatestSnapshot,
} from '@/components/overview/daily-snapshot-panel';
import type { DigestPayload } from '@/lib/snapshot-types';

/**
 * The daily digest, partitioned into a glanceable tabbed read (Market /
 * Equities / Risk / Actions). Shares the exact snapshot fetch the standalone
 * panel uses (useLatestSnapshot) and reuses its section renderers — this
 * replaces the single long scroll so the morning read is scannable. Nothing
 * from the old Overview right-column (actionable + risk) is lost; it moves
 * into the Risk/Actions tabs here.
 */

type TabKey = 'market' | 'equities' | 'risk' | 'actions';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'market', label: 'Market' },
  { key: 'equities', label: 'Equities' },
  { key: 'risk', label: 'Risk' },
  { key: 'actions', label: 'Actions' },
];

function TabBody({ tab, digest }: { tab: TabKey; digest: DigestPayload }) {
  if (tab === 'market') {
    return (
      <div className="space-y-5">
        <NarrativeSection title="Market regime" body={digest.market_regime_snapshot} testId="brief-regime" />
        <NarrativeSection title="Asset classes" body={digest.asset_classes_summary} testId="brief-asset-classes" />
        {digest.alt_data_dashboard.trim() && (
          <NarrativeSection title="Alt data" body={digest.alt_data_dashboard} testId="brief-alt-data" />
        )}
      </div>
    );
  }
  if (tab === 'equities') {
    return (
      <div className="space-y-5">
        <NarrativeSection title="US equities" body={digest.us_equities_summary} testId="brief-us-equities" />
        <NarrativeSection title="Institutional flows" body={digest.institutional_summary} testId="brief-institutional" />
        {digest.thesis_tracker.trim() && (
          <NarrativeSection title="Thesis tracker" body={digest.thesis_tracker} testId="brief-thesis" />
        )}
      </div>
    );
  }
  if (tab === 'risk') {
    return digest.risk_radar.length ? (
      <RiskList items={digest.risk_radar} />
    ) : (
      <p className="text-sm text-text-muted">No risks flagged for the latest run.</p>
    );
  }
  return digest.actionable_summary.length ? (
    <ActionableList items={digest.actionable_summary} />
  ) : (
    <p className="text-sm text-text-muted">No actionable items for the latest run.</p>
  );
}

const tabId = (k: TabKey) => `morning-brief-tab-${k}`;
const panelId = (k: TabKey) => `morning-brief-panel-${k}`;

export function MorningBriefPanel() {
  const { result, refetch } = useLatestSnapshot();
  const [tab, setTab] = useState<TabKey>('market');

  // Roving-tabindex arrow-key navigation to complete the ARIA tabs pattern.
  const onTablistKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const idx = TABS.findIndex((t) => t.key === tab);
    let next = idx;
    if (e.key === 'ArrowRight') next = (idx + 1) % TABS.length;
    else if (e.key === 'ArrowLeft') next = (idx - 1 + TABS.length) % TABS.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = TABS.length - 1;
    else return;
    e.preventDefault();
    setTab(TABS[next].key);
  };

  if (result === null) return <SnapshotSkeleton />;
  if (result.kind === 'error') return <SnapshotErrorBanner message={result.message} onRetry={refetch} />;
  if (result.kind === 'empty') return <SnapshotEmptyBanner reason={result.reason} />;

  const digest = result.envelope.digest;

  return (
    <section data-testid="morning-brief" className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border-subtle bg-bg-secondary flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Newspaper size={15} className="text-fin-blue shrink-0" />
          <h3 className="text-sm font-semibold shrink-0">Morning brief</h3>
          <span className="text-xs text-text-muted truncate hidden sm:inline">{digest.headline}</span>
        </div>
        <Link href="/research?tab=daily" className="text-[10px] text-fin-blue hover:underline font-medium shrink-0">
          Read full research →
        </Link>
      </div>

      <div
        role="tablist"
        aria-label="Daily digest sections"
        onKeyDown={onTablistKeyDown}
        className="flex gap-1 px-3 pt-3 border-b border-border-subtle overflow-x-auto"
      >
        {TABS.map((t) => {
          const active = t.key === tab;
          return (
            <button
              key={t.key}
              id={tabId(t.key)}
              role="tab"
              type="button"
              aria-selected={active}
              aria-controls={panelId(t.key)}
              tabIndex={active ? 0 : -1}
              onClick={() => setTab(t.key)}
              className={`shrink-0 rounded-t-md px-3.5 py-2 text-xs font-semibold transition-colors ${
                active
                  ? 'bg-bg-secondary text-text-primary border-b-2 border-fin-blue'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={panelId(tab)}
        aria-labelledby={tabId(tab)}
        tabIndex={0}
        className="p-5 sm:p-6"
      >
        <TabBody tab={tab} digest={digest} />
      </div>
    </section>
  );
}
