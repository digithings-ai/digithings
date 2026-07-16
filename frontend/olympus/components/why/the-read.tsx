'use client';

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
    <div className="space-y-6">
      <header className="space-y-3">
        <h1 className="font-display text-3xl sm:text-4xl tracking-tight text-ink">The read</h1>
        {digest.headline ? (
          <p className="text-sm sm:text-base leading-relaxed text-ink-soft max-w-3xl">
            {digest.headline}
          </p>
        ) : null}
        {freshEntries.length ? (
          <div className="flex flex-wrap gap-1.5" data-testid="read-freshness">
            {freshEntries.map(([seg, f]) => {
              const isToday = f.source === 'today';
              return (
                <span
                  key={seg}
                  className="inline-flex items-center gap-1 rounded-md border border-hair bg-ink/[0.04] px-1.5 py-0.5 text-[10px] text-ink-mute"
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

      {/* Lead — what Today summarized */}
      <NarrativeSection title="Market regime" body={digest.market_regime_snapshot} testId="read-regime" />

      <section className="grid gap-6 md:grid-cols-2">
        <div>
          {digest.actionable_summary.length ? (
            <ActionableList items={digest.actionable_summary} />
          ) : (
            <p className="text-sm text-ink-mute">No actionable items for the latest run.</p>
          )}
        </div>
        <div>
          {digest.risk_radar.length ? (
            <RiskList items={digest.risk_radar} />
          ) : (
            <p className="text-sm text-ink-mute">No risks flagged for the latest run.</p>
          )}
        </div>
      </section>

      {/* Deeper segments — collapsed by default so the lead stays scannable */}
      <div className="space-y-2">
        {DEEP_SECTIONS.map(({ key, title }) => {
          const body = String(digest[key] ?? '').trim();
          if (!body) return null;
          return (
            <details key={String(key)} className="glass-card px-5 py-3.5">
              <summary className="cursor-pointer text-sm font-semibold text-ink-soft hover:text-ink">
                {title}
              </summary>
              <p className="mt-3 text-sm leading-relaxed text-ink-soft whitespace-pre-line">{body}</p>
            </details>
          );
        })}
      </div>
    </div>
  );
}

export function TheRead() {
  const { result, refetch } = useLatestSnapshot();
  if (result === null) return <SnapshotSkeleton />;
  if (result.kind === 'error') return <SnapshotErrorBanner message={result.message} onRetry={refetch} />;
  if (result.kind === 'empty') return <SnapshotEmptyBanner reason={result.reason} />;
  return <TheReadBody digest={result.envelope.digest} />;
}
