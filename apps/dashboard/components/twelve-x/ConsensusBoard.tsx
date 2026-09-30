'use client';

import { useMemo } from 'react';
import { Button, Card, CompositionBar, ScoreBar, Sparkline } from '@digithings/ui/ui';
import { boardSummary, deriveBoardRows, stanceSegments } from '@/lib/twelve-x/board-view';
import { consensusScoreBarProps, scoreColorClass } from '@/lib/twelve-x/consensus-bar';
import { fmtSigned } from '@/lib/twelve-x/format';
import type { FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import DeltaChip from './DeltaChip';
import { useTwelveX } from './context';
import { TwelveXSectionHeading } from './TwelveXSectionHeading';

/**
 * Consensus board: per G10 currency, three encodings of the same series —
 * level (score bar: trailing 5-run average fill, today's actual as a tick),
 * history (30-run sparkline, dash when fewer than 5 runs) and composition
 * (stance mix share bar). Each row drills to that currency on the Consensus tab.
 * Today intentionally smooths; the Consensus tab plots raw per-run scores, and
 * both derive from the same `deriveConsensusRows`.
 */
export default function ConsensusBoard({
  series,
  disputedCurrencies,
}: {
  series: FxConsensusSnapshotRow[];
  /** Currencies to flag when the "data disputes" toggle is on. */
  disputedCurrencies?: ReadonlySet<string>;
}) {
  const { crossLink } = useTwelveX();
  const rows = useMemo(() => deriveBoardRows(series), [series]);

  return (
    <Card data-reveal className="flex flex-col gap-3 p-4" data-testid="consensus-board">
      <header className="flex items-baseline gap-2">
        <TwelveXSectionHeading>Consensus</TwelveXSectionHeading>
        <span className="ml-auto font-mono text-[10px] text-ink-mute">
          bar 5-run avg · tick today · line 30 runs
        </span>
      </header>

      {rows.length === 0 ? (
        <p className="py-6 text-center text-xs text-ink-mute">
          No consensus history yet — the board fills once a run is recorded.
        </p>
      ) : (
        <>
          <p className="sr-only">{boardSummary(rows)}</p>
          <ul className="flex flex-col gap-1.5" aria-label="Consensus by currency">
            {rows.map((r) => {
              const disputed = disputedCurrencies?.has(r.currency) ?? false;
              return (
                <li
                  key={r.currency}
                  data-ccy={r.currency}
                  data-disputed={disputed ? 'true' : undefined}
                  className="grid grid-cols-[2.75rem_minmax(5rem,1fr)_4.25rem_5rem_minmax(3rem,0.6fr)] items-center gap-2 sm:grid-cols-[2.75rem_minmax(6rem,1.4fr)_4.5rem_5.5rem_minmax(4rem,0.8fr)_4.25rem]"
                >
                  <Button
                    type="button"
                    variant="ghost"
                    size="xs"
                    className={`h-auto justify-start p-0 font-mono text-[13px] font-semibold hover:bg-transparent hover:text-accent ${
                      disputed ? 'text-warn' : 'text-ink'
                    }`}
                    title={`${r.currency}: ${r.label} — open on the Consensus tab`}
                    onClick={() => crossLink({ kind: 'currency', currency: r.currency })}
                  >
                    {r.currency}
                    {disputed ? <span aria-label="disputed by the data"> ●</span> : null}
                  </Button>
                  <ScoreBar
                    label={`${r.currency} 5-run average`}
                    {...consensusScoreBarProps(r.avgNow, { value: r.actualNow, label: "Today's actual" })}
                  />
                  <span
                    className={`text-right font-mono text-[12px] tabular-nums ${
                      r.avgNow === null ? 'text-ink-mute' : scoreColorClass(r.avgNow)
                    }`}
                  >
                    {fmtSigned(r.avgNow)}
                  </span>
                  {r.hasTrend ? (
                    <Sparkline
                      values={r.history}
                      tone="accent"
                      width={88}
                      height={22}
                      label={`${r.currency} consensus over the last ${r.history.length} runs`}
                    />
                  ) : (
                    <span
                      className="text-center font-mono text-[11px] text-ink-mute"
                      title="Fewer than 5 runs — no trend drawn"
                    >
                      —
                    </span>
                  )}
                  <CompositionBar
                    className="hidden sm:block"
                    height={6}
                    segments={stanceSegments(r.stance)}
                    label={`${r.currency} stance mix`}
                  />
                  <span className="text-right">
                    <DeltaChip delta={r.priorChange} />
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-hair pt-2 font-mono text-[10px] text-ink-mute">
            <span>Stance mix:</span>
            <span className="text-accent">bullish</span>
            <span className="text-warn">bearish</span>
            <span className="text-ink-soft">watch</span>
            <span>neutral</span>
            <span className="ml-auto">change vs prior run →</span>
          </p>
        </>
      )}
    </Card>
  );
}
