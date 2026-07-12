'use client';

import { AsOfBadge } from '@/components/shared/as-of-badge';
import type { AtlasRunDiagnostics } from '@/lib/types';

function isOk(status: string | null): boolean {
  const s = (status ?? '').toLowerCase();
  return s.includes('ok') || s.includes('success') || s === 'complete' || s === 'completed';
}

/** Most-recent run whose status reads as success (diagnostics are newest-first from the query). */
export function latestSuccessfulRun(diagnostics: AtlasRunDiagnostics[]): AtlasRunDiagnostics | null {
  return diagnostics.find((d) => isOk(d.status)) ?? null;
}

export function FreshnessBanner({ latest }: { latest: AtlasRunDiagnostics }) {
  const segs =
    latest.segments_total != null
      ? `${latest.segments_ok ?? 0}/${latest.segments_total} segments`
      : null;
  return (
    <div className="glass-card flex flex-wrap items-center gap-x-3 gap-y-1 p-4">
      <span className="inline-block h-2 w-2 shrink-0 rounded-full bg-[var(--accent)]" aria-hidden />
      <span className="text-sm text-ink">
        Last successful run{' '}
        <span className="font-medium">{latest.run_date ?? '—'}</span>
        {latest.run_type ? <span className="text-ink-soft"> · {latest.run_type}</span> : null}
        {segs ? <span className="text-ink-soft"> · {segs}</span> : null}
      </span>
      <AsOfBadge date={latest.run_date} createdAt={latest.created_at} />
    </div>
  );
}
