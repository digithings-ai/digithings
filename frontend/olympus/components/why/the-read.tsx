'use client';

import { ChevronRight } from 'lucide-react';
import {
  ActionableList,
  RiskList,
  NarrativeSection,
  SnapshotEmptyBanner,
  SnapshotErrorBanner,
  SnapshotSkeleton,
  useLatestSnapshot,
} from '@/components/overview/daily-snapshot-panel';
import type { DigestPayload } from '@/lib/snapshot-types';

/**
 * "The read" — the full research digest, structured so it is not eleven equal
 * walls of text. Leads with what Today summarizes (regime + actionable + risk
 * radar); the deeper segments are collapsed `<details>` the owner opens on
 * demand. Per-segment freshness badges mark what's from today vs carried from
 * the last baseline.
 */

const DEEP_SECTIONS: { key: keyof DigestPayload; title: string }[] = [
  { key: 'alt_data_dashboard', title: 'Alt data' },
  { key: 'institutional_summary', title: 'Institutional flows' },
  { key: 'asset_classes_summary', title: 'Asset classes' },
  { key: 'us_equities_summary', title: 'US equities' },
  { key: 'thesis_tracker', title: 'Thesis tracker' },
  { key: 'portfolio_recommendations', title: 'Portfolio recommendations' },
];

export function TheReadBody({ digest }: { digest: DigestPayload }) {
  const freshEntries = Object.entries(digest.segment_freshness ?? {});

  return (
    <section data-testid="why-read-workspace" className="divide-y divide-hair">
      <header className="space-y-3 pb-5">
        <p className="font-mono text-xs font-semibold uppercase text-ink-mute">
          Latest synthesis
        </p>
        {digest.headline ? (
          <h2 className="max-w-4xl font-display text-2xl leading-snug text-ink sm:text-3xl">
            {digest.headline}
          </h2>
        ) : null}
        {freshEntries.length ? (
          <div className="flex flex-wrap gap-1.5" data-testid="read-freshness">
            {freshEntries.map(([seg, f]) => {
              const isToday = f.source === 'today';
              return (
                <span
                  key={seg}
                  className="inline-flex items-center gap-1 rounded-md border border-hair bg-ink/[0.04] px-1.5 py-0.5 text-xs text-ink-mute"
                  title={isToday ? 'Refreshed in the latest run' : 'Carried from the last baseline'}
                >
                  <span
                    className={`h-1 w-1 rounded-full ${isToday ? 'bg-accent' : 'bg-ink-mute/50'}`}
                    aria-hidden
                  />
                  {seg}
                  <span className="text-ink-mute/70">
                    {isToday ? 'today' : `baseline${f.as_of ? ` ${f.as_of}` : ''}`}
                  </span>
                </span>
              );
            })}
          </div>
        ) : null}
      </header>

      <div className="py-5">
        <NarrativeSection title="Market regime" body={digest.market_regime_snapshot} testId="read-regime" />
      </div>

      <section className="grid gap-px bg-hair md:grid-cols-2">
        <div className="bg-surface py-5 md:pr-5">
          {digest.actionable_summary.length ? (
            <ActionableList items={digest.actionable_summary} flat />
          ) : (
            <p className="text-sm text-ink-mute">No actionable items for the latest run.</p>
          )}
        </div>
        <div className="bg-surface py-5 md:pl-5">
          {digest.risk_radar.length ? (
            <RiskList items={digest.risk_radar} flat />
          ) : (
            <p className="text-sm text-ink-mute">No risks flagged for the latest run.</p>
          )}
        </div>
      </section>

      <div data-testid="why-read-disclosures" className="divide-y divide-hair">
        {DEEP_SECTIONS.map(({ key, title }) => {
          const body = String(digest[key] ?? '').trim();
          if (!body) return null;
          return (
            <details key={String(key)} className="group py-4">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-ink-soft hover:text-ink">
                <span>{title}</span>
                <ChevronRight
                  size={16}
                  className="shrink-0 transition-transform group-open:rotate-90"
                  aria-hidden
                />
              </summary>
              <p className="mt-3 text-sm leading-relaxed text-ink-soft whitespace-pre-line">{body}</p>
            </details>
          );
        })}
      </div>
    </section>
  );
}

export function TheRead() {
  const { result, refetch } = useLatestSnapshot();
  if (result === null) return <SnapshotSkeleton flat />;
  if (result.kind === 'error') return <SnapshotErrorBanner message={result.message} onRetry={refetch} flat />;
  if (result.kind === 'empty') return <SnapshotEmptyBanner reason={result.reason} flat />;
  return <TheReadBody digest={result.envelope.digest} />;
}
