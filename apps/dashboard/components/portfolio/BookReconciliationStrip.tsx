'use client';

import Link from 'next/link';
import { Stat } from '@digithings/ui/ui';
import type { BookReconciliation } from '@/lib/book-reconciliation';
import { concentration } from '@/lib/book-view';
import { ledgerHref } from '@/lib/portfolio-url-state';

/**
 * Book summary as kit Stat tiles: invested / cash / positions / concentration,
 * plus the as-of stamp and the activity doorway. Exposure is not P&L, so no
 * tile carries an up/down tone.
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
  const conc = concentration(reconciliation.rows);

  return (
    <section data-testid="command-band" aria-label="Book exposure summary" className="space-y-2">
      <div data-region="metrics" className="grid grid-cols-2 gap-2 md:grid-cols-5">
        <Stat label="Invested" value={`${investedPct.toFixed(1)}%`} hint="of NAV" />
        <Stat label="Cash" value={`${cashPct.toFixed(1)}%`} hint="of NAV" />
        <Stat label="Positions" value={String(positionCount)} hint="held" />
        <Stat
          label="Top position"
          value={conc.top1 ? `${conc.top1.weightPct.toFixed(1)}%` : null}
          hint={conc.top1 ? conc.top1.ticker : 'none held'}
        />
        <Stat
          label="Top 5"
          value={conc.top1 ? `${conc.top5Pct.toFixed(1)}%` : null}
          hint={conc.effectiveN ? `≈ ${conc.effectiveN.toFixed(1)} equal bets` : 'of NAV'}
        />
      </div>
      <div
        data-region="identity"
        className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 font-mono text-[0.68rem] uppercase tracking-wider"
      >
        <Link
          href={ledgerHref()}
          className="text-accent hover:underline"
          data-testid="holdings-ledger-link"
        >
          Activity →
        </Link>
        {asOfDate ? (
          <span data-region="stamp" className="inline-flex items-baseline gap-1.5 text-ink-mute">
            as of <strong className="font-medium text-accent">{asOfDate}</strong>
          </span>
        ) : null}
      </div>
    </section>
  );
}
