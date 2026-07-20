'use client';

import type { AtlasRunDiagnostics } from '@/lib/types';

export function formatDuration(seconds: number | null): string {
  if (seconds == null || Number.isNaN(seconds)) return '—';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return remainder > 0 ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

export function RunEconomicsRow({ latest }: { latest: AtlasRunDiagnostics }) {
  const metrics = [
    { label: 'Duration', value: formatDuration(latest.duration_s) },
    {
      label: 'Segments produced',
      value:
        latest.segments_ok != null && latest.segments_total != null
          ? `${latest.segments_ok}/${latest.segments_total}`
          : '—',
    },
    { label: 'Carried', value: latest.segments_carried?.toString() ?? '—' },
    { label: 'Failed', value: latest.segments_failed?.toString() ?? '—' },
  ];

  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-[12px] border border-hair bg-hair md:grid-cols-4">
      {metrics.map((metric) => (
        <div key={metric.label} className="min-w-0 bg-surface p-4">
          <span className="block font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
            {metric.label}
          </span>
          <span className="mt-1 block font-mono text-xl tabular-nums text-ink">
            {metric.value}
          </span>
        </div>
      ))}
    </div>
  );
}
