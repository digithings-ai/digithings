'use client';

import type { BookReconciliation } from '@/lib/book-reconciliation';

/**
 * The restrained Holdings command band: invested exposure, position count,
 * and the book date. Cash is the inverse of invested; gross/net diagnostics
 * belong outside this monitoring view.
 */
export default function BookReconciliationStrip({
  reconciliation,
  asOfDate,
  positionCount,
}: {
  reconciliation: BookReconciliation;
  asOfDate: string | null;
  positionCount: number;
}) {
  const { investedPct } = reconciliation;

  return (
    <div
      data-testid="command-band"
      aria-label="Book exposure"
      className="grid grid-cols-1 items-stretch border-y border-hair bg-surface/80 sm:grid-cols-[minmax(14rem,1fr)_minmax(8rem,0.5fr)_auto]"
    >
      {/* Identity region — dominant Invested figure */}
      <div
        data-region="identity"
        className="flex flex-col justify-center gap-1.5 border-b border-hair px-5 py-5 sm:border-b-0 sm:border-r"
      >
        <span className="font-mono text-xs font-medium uppercase leading-tight tracking-normal text-ink-mute">
          invested
        </span>
        <strong className="font-mono text-5xl font-medium leading-none tabular-nums text-ink">
          {investedPct.toFixed(1)}%
        </strong>
      </div>

      <dl data-region="metrics" className="m-0 grid">
        <div className="flex min-w-0 flex-col justify-center gap-2 border-b border-hair px-5 py-4 sm:border-b-0 sm:border-r">
          <dt className="font-mono text-xs font-medium uppercase leading-tight tracking-normal text-ink-mute">
            positions
          </dt>
          <dd className="m-0 font-mono text-lg tabular-nums text-ink">{positionCount}</dd>
        </div>
      </dl>

      {/* As-of stamp */}
      {asOfDate && (
        <div
          data-region="stamp"
          className="flex min-w-0 flex-col items-start justify-center gap-1 border-t border-hair px-5 py-4 font-mono text-xs uppercase leading-tight tracking-normal text-ink-mute sm:min-w-[9rem] sm:items-end sm:border-t-0 sm:py-5"
        >
          <span>as of</span>
          <strong className="font-medium text-accent">{asOfDate}</strong>
        </div>
      )}
    </div>
  );
}
