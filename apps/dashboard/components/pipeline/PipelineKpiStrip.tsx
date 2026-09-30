'use client';

import { CompositionBar, Sparkline, Stat } from '@digithings/ui/ui';
import { formatDuration } from '@/components/system/run-economics-row';
import { formatDeltaPct, type PipelineDayKpis } from '@/lib/pipeline-kpis';

function show(n: number | null): string | null {
  return n == null ? null : String(n);
}

/** Per-day KPI tiles + segment/phase composition bars. Null-safe: missing telemetry is an em dash, never zero. */
export default function PipelineKpiStrip({ kpis }: { kpis: PipelineDayKpis }) {
  const { segments: s } = kpis;
  const hasSpark = kpis.durationSeries.some((v) => v != null);
  const segOk = s.ok ?? 0;
  const segCarried = s.carried ?? 0;
  const segFailed = s.failed ?? 0;

  return (
    <div data-testid="pipeline-kpi-strip" className="space-y-3">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-6">
        <Stat
          label="Duration"
          value={kpis.durationS != null ? formatDuration(kpis.durationS) : null}
          delta={formatDeltaPct(kpis.durationDeltaPct)}
          deltaTone={kpis.durationDeltaPct != null && kpis.durationDeltaPct > 25 ? 'warn' : 'mute'}
          spark={
            hasSpark ? (
              <Sparkline values={kpis.durationSeries} width={64} height={20} tone="accent" label="Run duration, last 30 days" />
            ) : undefined
          }
        />
        <Stat label="Segments ok" value={s.ok != null && s.total != null ? `${s.ok}/${s.total}` : null} />
        <Stat label="Carried" value={show(s.carried)} />
        <Stat label="Failed" value={show(s.failed)} delta={s.failed ? 'needs attention' : null} deltaTone="warn" />
        <Stat
          label="Attempts"
          value={show(kpis.attempts)}
          delta={kpis.attempts != null && kpis.attempts > 1 ? 'retried' : null}
          deltaTone="warn"
        />
        <Stat label="Artifacts" value={String(kpis.artifacts)} />
      </div>

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
