'use client';

import type { DeltaRequestMeta } from '@/lib/types';

/**
 * Compact banner: deltas ran this day; details appear inline when opening highlighted files (digest = review diff).
 */
export default function DeltaDaySummary({
  meta,
  digestAvailable,
  onOpenDigest,
}: {
  meta: DeltaRequestMeta;
  digestAvailable: boolean;
  onOpenDigest: () => void;
}) {
  const pathCount = new Set([...meta.changed_paths, ...meta.op_paths].filter(Boolean)).size;
  const opCount = meta.op_paths.length;
  const baseline = meta.baseline_date?.trim();

  return (
    <div
      className="rounded-xl border border-accent/35 bg-gradient-to-br from-accent/[0.12] via-accent/[0.06] to-transparent px-5 py-5 text-sm shadow-[0_0_48px_-12px_color-mix(in_srgb,var(--accent)_35%,transparent)] ring-1 ring-inset ring-ink/[0.06]"
      role="region"
      aria-label="Delta run summary"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-1.5 min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-accent/90">Delta day</p>
          <p className="text-lg font-semibold text-ink leading-snug">Updates applied to this run</p>
          <p className="text-xs text-ink-soft">
            {pathCount} path{pathCount !== 1 ? 's' : ''} touched
            {opCount > 0 ? (
              <>
                {' '}
                · {opCount} op{opCount !== 1 ? 's' : ''}
              </>
            ) : null}
          </p>
          <p className="text-xs text-ink-mute max-w-2xl">
            Open the <strong className="text-ink-soft">digest</strong> to compare against the prior snapshot or
            the delta baseline
            {baseline ? (
              <>
                {' '}
                (<span className="font-mono text-ink-soft">{baseline}</span>)
              </>
            ) : null}
            .
          </p>
        </div>
        {digestAvailable ? (
          <button
            type="button"
            onClick={onOpenDigest}
            className="shrink-0 text-sm font-semibold px-4 py-2.5 rounded-lg bg-accent/25 text-accent border border-accent/40 hover:bg-accent/35 transition-colors"
          >
            Open digest
          </button>
        ) : null}
      </div>
    </div>
  );
}
