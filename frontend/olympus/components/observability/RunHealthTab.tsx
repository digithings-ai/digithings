'use client';

import type { ViewRow } from '@/lib/database.types';
import { EmptyState, SectionCard, StatTile, fmtNum } from './shared';

function statusColor(status: string | null): string {
  const s = (status ?? '').toLowerCase();
  if (s.includes('ok') || s.includes('success') || s === 'complete' || s === 'completed')
    return 'text-fin-green';
  if (s.includes('fail') || s.includes('error') || s.includes('abort')) return 'text-fin-red';
  if (s) return 'text-fin-amber';
  return 'text-text-secondary';
}

function fmtDuration(s: number | null): string {
  if (s == null) return '—';
  if (s < 90) return `${s.toFixed(0)}s`;
  return `${(s / 60).toFixed(1)}m`;
}

export default function RunHealthTab({
  runHealth,
  available,
}: {
  runHealth: ViewRow<'atlas_run_health'>[];
  available: boolean;
}) {
  if (!available) {
    return (
      <EmptyState
        title="Run-health view not yet enabled"
        message="The curated atlas_run_health view (migration 041) exposes run status, segment success/carry/fail counts, model, and timing — but never spend telemetry. It requires owner sign-off before it goes live, so this panel stays empty until the migration is applied."
      />
    );
  }
  if (!runHealth.length) {
    return (
      <EmptyState
        title="No runs recorded yet"
        message="The pipeline writes a diagnostics row at the end of each Atlas/Hermes run. Once a baseline or delta run completes, its health will appear here."
      />
    );
  }

  const latest = runHealth[0];

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile
          label="Latest status"
          value={latest.status ?? '—'}
          sub={latest.run_date ?? undefined}
          color={statusColor(latest.status)}
        />
        <StatTile label="Run type" value={latest.run_type ?? '—'} />
        <StatTile
          label="Segments OK"
          value={`${fmtNum(latest.segments_ok)}/${fmtNum(latest.segments_total)}`}
          color="text-fin-green"
        />
        <StatTile label="Carried" value={fmtNum(latest.segments_carried)} color="text-fin-amber" />
        <StatTile
          label="Failed"
          value={fmtNum(latest.segments_failed)}
          color={(latest.segments_failed ?? 0) > 0 ? 'text-fin-red' : 'text-text-secondary'}
        />
        <StatTile label="Duration" value={fmtDuration(latest.duration_s)} sub={latest.model ?? undefined} />
      </div>

      <SectionCard
        title="Recent runs"
        subtitle="Health of the last 30 pipeline runs — status, segment outcomes, model, and timing. Spend telemetry is intentionally excluded from this surface."
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-left text-xs text-text-muted border-b border-border-subtle">
                <th className="py-2 pr-4 font-medium">Date</th>
                <th className="py-2 pr-4 font-medium">Type</th>
                <th className="py-2 pr-4 font-medium">Status</th>
                <th className="py-2 pr-4 font-medium text-right">OK</th>
                <th className="py-2 pr-4 font-medium text-right">Carried</th>
                <th className="py-2 pr-4 font-medium text-right">Failed</th>
                <th className="py-2 pr-4 font-medium text-right">Total</th>
                <th className="py-2 pr-4 font-medium">Model</th>
                <th className="py-2 font-medium text-right">Duration</th>
              </tr>
            </thead>
            <tbody>
              {runHealth.map((r) => (
                <tr key={r.run_id} className="border-b border-border-subtle/50">
                  <td className="py-2 pr-4 text-text-primary">{r.run_date ?? '—'}</td>
                  <td className="py-2 pr-4 text-text-secondary">{r.run_type ?? '—'}</td>
                  <td className={`py-2 pr-4 ${statusColor(r.status)}`}>{r.status ?? '—'}</td>
                  <td className="py-2 pr-4 text-right text-fin-green">{fmtNum(r.segments_ok)}</td>
                  <td className="py-2 pr-4 text-right text-fin-amber">{fmtNum(r.segments_carried)}</td>
                  <td
                    className={`py-2 pr-4 text-right ${(r.segments_failed ?? 0) > 0 ? 'text-fin-red' : 'text-text-secondary'}`}
                  >
                    {fmtNum(r.segments_failed)}
                  </td>
                  <td className="py-2 pr-4 text-right text-text-secondary">{fmtNum(r.segments_total)}</td>
                  <td className="py-2 pr-4 text-text-muted truncate max-w-[180px]">{r.model ?? '—'}</td>
                  <td className="py-2 text-right text-text-secondary">{fmtDuration(r.duration_s)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
