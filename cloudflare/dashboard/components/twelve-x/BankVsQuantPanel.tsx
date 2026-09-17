'use client';

import { useMemo, useState } from 'react';
import { Card } from '@digithings/web/ui';
import type { FxConsensusDivergence } from '@/lib/twelve-x/types';
import type { ConsensusCurrencyRow } from '@/lib/twelve-x/consensus-view';
import { currencyColor } from '@/lib/twelve-x/consensus-bar';
import { fmtSigned } from '@/lib/twelve-x/format';
import { ConsensusScoreBar } from './ConsensusScoreBars';
import DivergencePanel from './DivergencePanel';

export interface BankVsQuantRow {
  currency: string;
  label: string;
  streetScore: number;
  quantScore: number;
  gap: number;
  isDivergent: boolean;
}

/**
 * PURE — join the street-vs-quant divergence map with the consensus rows and
 * sort divergent-first (then gap descending), so the currencies where the desk
 * disagrees with the quant read head the table.
 */
export function buildBankVsQuantRows(
  divergenceByCurrency: Record<string, FxConsensusDivergence>,
  consensusRows: ConsensusCurrencyRow[],
): BankVsQuantRow[] {
  const labelByCcy = new Map(consensusRows.map((r) => [r.currency, r.label]));
  const rows: BankVsQuantRow[] = Object.entries(divergenceByCurrency).map(([currency, div]) => ({
    currency,
    label: labelByCcy.get(currency) ?? '',
    streetScore: div.consensusScore,
    quantScore: div.pmtScore,
    gap: div.gap,
    isDivergent: div.isDivergent,
  }));
  return rows.sort((a, b) => {
    if (a.isDivergent !== b.isDivergent) return a.isDivergent ? -1 : 1;
    return b.gap - a.gap;
  });
}

/**
 * Bank-vs-quant corroboration panel: one row per currency with TWO
 * `ConsensusScoreBar`s (street consensus vs PMT Smart Bias on the shared
 * −2…+2 scale), divergent-first. Selecting a row reuses `DivergencePanel`
 * for the full both-reads detail.
 */
export function BankVsQuantPanel({
  divergenceByCurrency,
  consensusRows,
}: {
  divergenceByCurrency: Record<string, FxConsensusDivergence>;
  consensusRows: ConsensusCurrencyRow[];
}) {
  const [selectedCcy, setSelectedCcy] = useState<string | null>(null);
  const rows = useMemo(
    () => buildBankVsQuantRows(divergenceByCurrency, consensusRows),
    [divergenceByCurrency, consensusRows],
  );
  const selected = selectedCcy ? divergenceByCurrency[selectedCcy] ?? null : null;

  if (rows.length === 0) {
    return (
      <Card data-reveal className="gap-0 p-5" data-testid="bank-vs-quant">
        <p className="font-mono text-xs font-medium uppercase tracking-[0.08em] text-ink-soft">
          Bank vs quant
        </p>
        <p className="mt-2 text-sm text-ink-mute">No street-vs-quant reads for this run.</p>
      </Card>
    );
  }

  return (
    <Card data-reveal className="gap-0 space-y-2 p-5" data-testid="bank-vs-quant">
      <p className="font-mono text-xs font-medium uppercase tracking-[0.08em] text-ink-soft">
        Bank vs quant · {rows.filter((r) => r.isDivergent).length} divergent
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-xs">
          <thead>
            <tr className="border-b border-hair text-[10px] uppercase tracking-wider text-ink-mute">
              <th className="px-3 py-2 text-left font-medium">Currency</th>
              <th className="px-3 py-2 text-left font-medium">Street</th>
              <th className="px-3 py-2 text-left font-medium">Quant (PMT)</th>
              <th className="px-3 py-2 text-right font-medium">Gap</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hair">
            {rows.map((row) => (
              <tr key={row.currency}>
                <td className="whitespace-nowrap px-3 py-2">
                  <button
                    type="button"
                    onClick={() => setSelectedCcy(row.currency)}
                    className="text-left hover:underline"
                    title={row.label || row.currency}
                  >
                    <span
                      className="font-mono font-semibold text-[13px]"
                      style={{ color: currencyColor(row.currency) }}
                    >
                      {row.currency}
                    </span>
                    {row.isDivergent ? (
                      <span className="ml-1.5 border border-warn px-1 font-mono text-[10px] text-warn">
                        DIV
                      </span>
                    ) : null}
                  </button>
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="flex min-w-[100px] flex-1">
                      <ConsensusScoreBar value={row.streetScore} />
                    </div>
                    <span className="font-mono tabular-nums text-ink-soft">
                      {fmtSigned(row.streetScore)}
                    </span>
                  </div>
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="flex min-w-[100px] flex-1">
                      <ConsensusScoreBar value={row.quantScore} />
                    </div>
                    <span className="font-mono tabular-nums text-ink-soft">
                      {fmtSigned(row.quantScore)}
                    </span>
                  </div>
                </td>
                <td className="whitespace-nowrap px-3 py-2 text-right font-mono tabular-nums text-ink">
                  {row.gap.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <DivergencePanel
        open={!!selected}
        divergence={selected}
        onClose={() => setSelectedCcy(null)}
      />
    </Card>
  );
}

export default BankVsQuantPanel;
