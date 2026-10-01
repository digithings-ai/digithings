'use client';

import type { ReactNode } from 'react';
import { Badge, CompositionBar, Sparkline } from '@digithings/ui/ui';
import { formatDuration } from '@/components/system/run-economics-row';
import { formatDeltaPct, type PipelineDayKpis } from '@/lib/pipeline-kpis';

function show(n: number | null): string {
  return n == null ? '—' : String(n);
}

type ChipVariant = 'neutral' | 'accent' | 'warn';

function Chip({ label, children, variant = 'neutral', testId }: { label: string; children: ReactNode; variant?: ChipVariant; testId?: string }) {
  return (
    <Badge variant={variant} data-testid={testId} className="gap-1.5 font-mono tabular-nums">
      <span className="text-[0.6rem] uppercase tracking-wider text-ink-mute">{label}</span>
      <span>{children}</span>
    </Badge>
  );
}

/**
 * Single dense inline row of run KPIs (~one badge tall): duration (+ sparkline, + delta only when
 * comparable), segments ok/total, carried, failed, attempts, artifacts. Null-safe: missing
 * telemetry is an em dash, never zero. Carried is informational (mute); only failures and
 * retries are warn.
 */
export default function PipelineKpiStrip({ kpis }: { kpis: PipelineDayKpis }) {
  const { segments: s } = kpis;
  const hasSpark = kpis.durationSeries.some((v) => v != null);
  const delta = formatDeltaPct(kpis.durationDeltaPct);

  return (
    <div data-testid="pipeline-kpi-strip" className="flex flex-wrap items-center gap-1.5">
      <Chip label="Duration" variant={kpis.durationDeltaPct != null && kpis.durationDeltaPct > 25 ? 'warn' : 'neutral'}>
        {kpis.durationS != null ? formatDuration(kpis.durationS) : '—'}
        {delta ? <span className="text-ink-mute"> {delta}{kpis.runType ? ` (${kpis.runType})` : ''}</span> : null}
      </Chip>
      {hasSpark && (
        <Sparkline values={kpis.durationSeries} width={56} height={16} tone="accent" label="Run duration, last 30 days" />
      )}
      <Chip label="Segments">{s.ok != null && s.total != null ? `${s.ok}/${s.total}` : '—'}</Chip>
      <Chip label="Carried">{show(s.carried)}</Chip>
      <Chip label="Failed" variant={s.failed ? 'warn' : 'neutral'}>
        {show(s.failed)}
      </Chip>
      <Chip label="Attempts" variant={kpis.attempts != null && kpis.attempts > 1 ? 'warn' : 'neutral'}>
        {show(kpis.attempts)}
      </Chip>
      <Chip label="Artifacts">{String(kpis.artifacts)}</Chip>
    </div>
  );
}

/** Expanded detail behind the run-health collapse: segment composition + per-phase bars. */
export function PipelineKpiDetail({ kpis }: { kpis: PipelineDayKpis }) {
  const { segments: s } = kpis;
  const segOk = s.ok ?? 0;
  const segCarried = s.carried ?? 0;
  const segFailed = s.failed ?? 0;

  return (
    <div data-testid="pipeline-kpi-detail" className="space-y-3">
      {s.total != null && s.total > 0 && (
        <CompositionBar
          mode="stacked"
          total={s.total}
          height={10}
          legend
          label={`Segments: ${segOk} ok, ${segCarried} carried, ${segFailed} failed of ${s.total}`}
          segments={[
            { key: 'ok', label: 'ok', value: segOk, tone: 'accent' },
            { key: 'carried', label: 'carried', value: segCarried, tone: 'mute' },
            { key: 'failed', label: 'failed', value: segFailed, tone: 'warn' },
          ]}
        />
      )}

      {kpis.phases.length > 0 && (
        <div data-testid="pipeline-phase-health" className="grid gap-x-4 gap-y-1.5 md:grid-cols-2">
          {kpis.phases.map((p) => (
            <div key={p.phase} className="flex items-center gap-2 font-mono text-[0.65rem] text-ink-mute">
              <span className="w-14 shrink-0 uppercase tracking-wider">Phase {p.phase}</span>
              <CompositionBar
                className="min-w-0 flex-1"
                height={6}
                label={`Phase ${p.phase}: ${p.ok} ok, ${p.carried} carried, ${p.failed} failed`}
                segments={[
                  { key: 'ok', label: 'ok', value: p.ok, tone: 'accent' },
                  { key: 'carried', label: 'carried', value: p.carried, tone: 'mute' },
                  { key: 'failed', label: 'failed', value: p.failed, tone: 'warn' },
                ]}
              />
              <span className="w-16 shrink-0 text-right tabular-nums">
                {p.ok}/{p.ok + p.carried + p.failed}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
