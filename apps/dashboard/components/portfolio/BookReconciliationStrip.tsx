'use client';

import type { BookReconciliation } from '@/lib/book-reconciliation';
import Link from 'next/link';
import { ledgerHref } from '@/lib/portfolio-url-state';

/**
 * Slim Holdings summary: invested / cash / count / as-of in one compact row so
 * the positions table owns the viewport on mobile and desktop.
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
  const { investedPct, cashPct } = reconciliation;

  return (
    <div
      data-testid="command-band"
      aria-label="Book exposure summary"
      className="flex flex-wrap items-baseline gap-x-5 gap-y-1 border-y border-hair bg-surface/80 px-4 py-2.5 font-mono text-[0.68rem] md:px-6"
    >
      <div data-region="identity" className="inline-flex items-baseline gap-2">
        <span className="uppercase tracking-wider text-ink-mute">Invested</span>
        <strong className="text-base font-medium tabular-nums text-ink">
          {investedPct.toFixed(1)}%
        </strong>
      </div>
      <div data-region="metrics" className="inline-flex flex-wrap items-baseline gap-x-5 gap-y-1 text-ink-soft">
        <span>
          <span className="uppercase tracking-wider text-ink-mute">Cash </span>
          <span className="tabular-nums text-ink">{cashPct.toFixed(1)}%</span>
        </span>
        <span>
          <span className="uppercase tracking-wider text-ink-mute">Positions </span>
          <span className="tabular-nums text-ink">{positionCount}</span>
        </span>
        <Link
          href={ledgerHref()}
          className="uppercase tracking-wider text-accent hover:underline"
          data-testid="holdings-ledger-link"
        >
          Activity →
        </Link>
      </div>
      {asOfDate ? (
        <div
          data-region="stamp"
          className="ml-auto inline-flex items-baseline gap-1.5 uppercase tracking-wider text-ink-mute"
        >
          <span>as of</span>
          <strong className="font-medium text-accent">{asOfDate}</strong>
        </div>
      ) : null}
    </div>
  );
}
