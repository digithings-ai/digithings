'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Badge, SectionTitle } from '@/components/ui';
import { fetchLatestSnapshot } from '@/lib/snapshot-fetch';
import type {
  ActionableItem,
  DigestPayload,
  RiskItem,
  SnapshotBias,
  SnapshotEnvelope,
  SnapshotFetchResult,
} from '@/lib/snapshot-types';
import {
  DEFAULT_SNAPSHOT_STALENESS_HOURS,
  formatAge,
  isStale,
} from '@/lib/snapshot-staleness';

export const BIAS_VARIANT: Record<SnapshotBias, 'green' | 'red' | 'amber' | 'blue' | 'default'> = {
  strong_bullish: 'green',
  bullish: 'green',
  neutral: 'blue',
  bearish: 'red',
  strong_bearish: 'red',
  mixed: 'amber',
};

export function biasLabel(bias: SnapshotBias): string {
  return bias.replace(/_/g, ' ');
}

/**
 * Fetch the latest snapshot envelope in an effect, with a refetch handle.
 * Extracted so the Morning Brief (tabbed view) can share the exact same
 * network path as the standalone panel without duplicating the effect.
 */
export function useLatestSnapshot(): {
  result: SnapshotFetchResult | null;
  refetch: () => void;
} {
  const [reloadTick, setReloadTick] = useState(0);
  const [result, setResult] = useState<SnapshotFetchResult | null>(null);

  const refetch = useCallback(() => {
    setResult(null);
    setReloadTick((n) => n + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchLatestSnapshot()
      .then((next) => {
        if (!cancelled) setResult(next);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setResult({
          kind: 'error',
          message: err instanceof Error ? err.message : String(err),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  return { result, refetch };
}

export interface DailySnapshotPanelProps {
  /** Inject a fetch result for tests (skips network). */
  fetchResult?: SnapshotFetchResult;
  /** Override "now" for staleness checks (tests). */
  now?: Date;
}

export function DailySnapshotPanel({ fetchResult, now }: DailySnapshotPanelProps) {
  // Tests inject `fetchResult` directly — render synchronously without an
  // effect. Production renders defer to `<DailySnapshotPanelLive />`, which
  // owns the network fetch in an effect.
  if (fetchResult) {
    return <RenderResult result={fetchResult} now={now} />;
  }
  return <DailySnapshotPanelLive now={now} />;
}

function DailySnapshotPanelLive({ now }: { now?: Date }) {
  const { result, refetch } = useLatestSnapshot();
  if (result === null) return <SnapshotSkeleton />;
  return <RenderResult result={result} now={now} onRetry={refetch} />;
}

function RenderResult({
  result,
  now,
  onRetry,
}: {
  result: SnapshotFetchResult;
  now?: Date;
  onRetry?: () => void;
}) {
  if (result.kind === 'error') {
    return (
      <SnapshotErrorBanner
        message={result.message}
        onRetry={onRetry ?? (() => undefined)}
      />
    );
  }
  if (result.kind === 'empty') {
    return <SnapshotEmptyBanner reason={result.reason} />;
  }
  return <SnapshotContent envelope={result.envelope} now={now} />;
}

export function SnapshotSkeleton() {
  return (
    <section
      data-testid="snapshot-loading"
      aria-busy="true"
      aria-label="Loading daily snapshot"
      className="glass-card p-6 space-y-4 animate-pulse"
    >
      <div className="h-3 w-40 rounded bg-ink/10" />
      <div className="h-6 w-3/4 rounded bg-ink/10" />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="h-20 rounded bg-ink/5" />
        <div className="h-20 rounded bg-ink/5" />
      </div>
    </section>
  );
}

export function SnapshotErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <section
      data-testid="snapshot-error"
      role="alert"
      className="glass-card p-5 border-down/30 bg-down/5"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <SectionTitle className="text-down">Snapshot unavailable</SectionTitle>
          <p className="text-sm text-ink-soft break-words">{message}</p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 rounded-md border border-down/40 bg-down/10 px-3 py-1.5 text-xs font-semibold text-down hover:bg-down/20"
        >
          Retry
        </button>
      </div>
    </section>
  );
}

export function SnapshotEmptyBanner({ reason }: { reason: 'no_recent_row' | 'unconfigured' }) {
  const message =
    reason === 'unconfigured'
      ? 'Supabase credentials are not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.'
      : 'No snapshot has been published for today or yesterday yet. Check back after the next pipeline run.';
  return (
    <section
      data-testid="snapshot-empty"
      role="status"
      className="glass-card p-5 border-hair bg-term-bg/40"
    >
      <SectionTitle>No snapshot available</SectionTitle>
      <p className="text-sm text-ink-soft">{message}</p>
    </section>
  );
}

function SnapshotContent({
  envelope,
  now,
}: {
  envelope: SnapshotEnvelope;
  now?: Date;
}) {
  const stale = useMemo(
    () => isStale(envelope.published_at, DEFAULT_SNAPSHOT_STALENESS_HOURS, now ?? new Date()),
    [envelope.published_at, now],
  );
  const age = useMemo(
    () => formatAge(envelope.published_at, now ?? new Date()),
    [envelope.published_at, now],
  );
  const digest = envelope.digest;

  return (
    <section data-testid="snapshot-present" className="space-y-4">
      {stale && (
        <div
          data-testid="snapshot-stale-banner"
          role="status"
          className="glass-card p-4 border-warn/40 bg-warn/5 flex items-center justify-between gap-3"
        >
          <div>
            <p className="text-sm font-semibold text-warn">Stale snapshot</p>
            <p className="text-xs text-ink-soft">
              Published {age ?? 'unknown'} (older than {DEFAULT_SNAPSHOT_STALENESS_HOURS}h).
            </p>
          </div>
          <Badge variant="amber">stale</Badge>
        </div>
      )}

      <article className="glass-card p-6 space-y-5">
        <header className="flex flex-wrap items-baseline justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-widest text-ink-mute">
              Daily snapshot
            </p>
            <h2
              data-testid="snapshot-headline"
              className="text-xl font-semibold leading-snug text-ink"
            >
              {digest.headline}
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-ink-mute">
            <Badge variant={BIAS_VARIANT[digest.bias] ?? 'default'} data-testid="snapshot-bias">
              {biasLabel(digest.bias)}
            </Badge>
            <span data-testid="snapshot-segment">{digest.segment}</span>
            <span aria-hidden="true">·</span>
            <span data-testid="snapshot-run-date">{envelope.run_date}</span>
            <span aria-hidden="true">·</span>
            <span data-testid="snapshot-run-type" className="uppercase tracking-wider">
              {envelope.run_type}
            </span>
            {age && (
              <>
                <span aria-hidden="true">·</span>
                <span data-testid="snapshot-published-age">{age}</span>
              </>
            )}
          </div>
        </header>

        <NarrativeSection title="Market regime" body={digest.market_regime_snapshot} testId="snapshot-section-regime" />
        <NarrativeSection title="Alt data" body={digest.alt_data_dashboard} testId="snapshot-section-alt-data" />
        <NarrativeSection title="Institutional flows" body={digest.institutional_summary} testId="snapshot-section-institutional" />
        <NarrativeSection title="Asset classes" body={digest.asset_classes_summary} testId="snapshot-section-asset-classes" />
        <NarrativeSection title="US equities" body={digest.us_equities_summary} testId="snapshot-section-us-equities" />

        {digest.thesis_tracker.trim().length > 0 && (
          <NarrativeSection title="Thesis tracker" body={digest.thesis_tracker} testId="snapshot-section-thesis" />
        )}
        {digest.portfolio_recommendations.trim().length > 0 && (
          <NarrativeSection
            title="Portfolio recommendations"
            body={digest.portfolio_recommendations}
            testId="snapshot-section-portfolio-recs"
          />
        )}

        <ActionableList items={digest.actionable_summary} />
        <RiskList items={digest.risk_radar} />
      </article>
    </section>
  );
}

export function NarrativeSection({ title, body, testId }: { title: string; body: string; testId: string }) {
  return (
    <div data-testid={testId} className="space-y-1.5">
      <h3 className="text-[10px] font-semibold uppercase tracking-widest text-ink-mute">
        {title}
      </h3>
      <p className="text-sm leading-relaxed text-ink-soft whitespace-pre-line">{body}</p>
    </div>
  );
}

export function ActionableList({ items }: { items: ActionableItem[] }) {
  if (!items.length) return null;
  return (
    <div data-testid="snapshot-actionable" className="space-y-2">
      <h3 className="text-[10px] font-semibold uppercase tracking-widest text-ink-mute">
        Actionable summary
      </h3>
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li
            key={`${item.priority}-${i}`}
            data-testid="snapshot-actionable-item"
            className="rounded-md border border-hair bg-term-bg/30 p-3 text-sm"
          >
            <div className="flex items-center gap-2 text-xs text-ink-mute">
              <span className="font-mono">P{item.priority}</span>
              <span aria-hidden="true">·</span>
              <span className="font-semibold text-ink">{item.label}</span>
            </div>
            <p className="mt-1 text-ink-soft">{item.rationale}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RiskList({ items }: { items: RiskItem[] }) {
  if (!items.length) return null;
  return (
    <div data-testid="snapshot-risk-radar" className="space-y-2">
      <h3 className="text-[10px] font-semibold uppercase tracking-widest text-ink-mute">
        Risk radar
      </h3>
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li
            key={`${item.label}-${i}`}
            data-testid="snapshot-risk-item"
            className="rounded-md border border-hair bg-term-bg/30 p-3 text-sm"
          >
            <div className="flex items-center gap-2 text-xs text-ink-mute">
              <span className="font-mono">{item.horizon_hours}h</span>
              <span aria-hidden="true">·</span>
              <span className="font-semibold text-ink">{item.label}</span>
            </div>
            <p className="mt-1 text-ink-soft">{item.trigger}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Re-export for tests that want to assert against the digest field set. */
export type { DigestPayload, SnapshotEnvelope };
