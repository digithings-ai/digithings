'use client';

import type { BookReconciliation } from '@/lib/book-reconciliation';

/**
 * The single weight headline for Holdings (F3). Held positions + cash = 100%.
 * Gross/Net only render when the book is levered (gross !== invested) — today it
 * is unlevered, so the strip stays a clean two-tile Invested / Cash readout.
 */
export default function BookReconciliationStrip({
  reconciliation,
  asOfDate,
}: {
  reconciliation: BookReconciliation;
  asOfDate: string | null;
}) {
  const { investedPct, cashPct, grossPct, netPct } = reconciliation;
  const levered =
    Math.abs(grossPct - investedPct) > 0.05 || Math.abs(netPct - investedPct) > 0.05;
  return (
    <div className="glass-card flex flex-wrap items-center justify-between gap-x-8 gap-y-3 px-4 py-4 md:px-6">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-mute">Invested</p>
          <p className="mt-0.5 font-mono text-2xl tabular-nums text-ink">
            {investedPct.toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-ink-mute">Cash</p>
          <p className="mt-0.5 font-mono text-2xl tabular-nums text-ink-soft">
            {cashPct.toFixed(1)}%
          </p>
        </div>
        {levered && (
          <>
            <div>
              <p className="text-xs uppercase tracking-wider text-ink-mute">Gross</p>
              <p className="mt-0.5 font-mono text-2xl tabular-nums text-ink">
                {grossPct.toFixed(1)}%
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wider text-ink-mute">Net</p>
              <p className="mt-0.5 font-mono text-2xl tabular-nums text-ink">
                {netPct.toFixed(1)}%
              </p>
            </div>
          </>
        )}
      </div>
      {asOfDate && <p className="font-mono text-xs text-ink-mute">as of {asOfDate}</p>}
    </div>
  );
}
