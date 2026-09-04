'use client';

import { useMemo } from 'react';
import { ClipboardList } from 'lucide-react';
import type {
  FxConsensusEvalRow,
  FxIdeaEvalRow,
  FxTradeIdeaRow,
} from '@/lib/twelve-x/types';
import {
  assembleTradeHistory,
  formatHoldPct,
  type TradeHistoryRow,
} from '@/lib/twelve-x/trade-history';
import {
  openIdeas,
  summarizeConsensusAccuracy,
  summarizeConsensusStability,
  summarizeIdeaOutcomes,
} from '@/lib/twelve-x/track-record';
import { formatWilsonPct } from '@/lib/twelve-x/wilson';

function RateCard({
  title,
  subtitle,
  primary,
  longLabel,
  shortLabel,
}: {
  title: string;
  subtitle?: string;
  primary: string;
  longLabel?: string;
  shortLabel?: string;
}) {
  return (
    <div className="space-y-1 border border-hair bg-surface/40 px-3 py-2.5">
      <p className="text-[11px] font-medium uppercase tracking-wider text-ink-mute">{title}</p>
      {subtitle ? <p className="text-[10px] text-ink-mute">{subtitle}</p> : null}
      <p className="font-mono text-sm tabular-nums text-ink">{primary}</p>
      {longLabel || shortLabel ? (
        <p className="text-[10px] text-ink-mute">
          {longLabel ? <span>Long {longLabel}</span> : null}
          {longLabel && shortLabel ? <span> · </span> : null}
          {shortLabel ? <span>Short {shortLabel}</span> : null}
        </p>
      ) : null}
    </div>
  );
}

function Pill({ tone, children }: { tone: 'live' | 'right' | 'wrong' | 'mute'; children: string }) {
  const toneClass =
    tone === 'right'
      ? 'border-accent text-accent'
      : tone === 'wrong'
        ? 'border-warn text-warn'
        : tone === 'live'
          ? 'border-ink text-ink'
          : 'border-hair text-ink-mute';
  return (
    <span className={`inline-block border px-1.5 font-mono text-[10px] ${toneClass}`}>
      {children}
    </span>
  );
}

function BiasPill({ row }: { row: TradeHistoryRow }) {
  if (row.lifecycle === 'live') return <Pill tone="live">LIVE</Pill>;
  if (row.lifecycle === 'no_data') return <Pill tone="mute">NO DATA</Pill>;
  if (row.lifecycle === 'unscored') return <Pill tone="mute">—</Pill>;
  if (row.directionalWin === true) return <Pill tone="right">RIGHT</Pill>;
  if (row.directionalWin === false) return <Pill tone="wrong">WRONG</Pill>;
  return <Pill tone="mute">—</Pill>;
}

export default function TradesTab({
  ideas,
  ideaEval,
  consensusEval,
}: {
  ideas: FxTradeIdeaRow[];
  ideaEval: FxIdeaEvalRow[];
  consensusEval: FxConsensusEvalRow[];
}) {
  const history = useMemo(() => assembleTradeHistory(ideas, ideaEval), [ideas, ideaEval]);
  const ideaSummary = useMemo(() => summarizeIdeaOutcomes(ideaEval), [ideaEval]);
  const open = useMemo(() => openIdeas(ideaEval), [ideaEval]);
  const stability = useMemo(() => summarizeConsensusStability(consensusEval), [consensusEval]);
  const accuracy = useMemo(() => summarizeConsensusAccuracy(consensusEval), [consensusEval]);

  const weightedStab = stability.find((s) => s.weighted);
  const unweightedStab = stability.find((s) => !s.weighted);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <ClipboardList size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-2xl tracking-tight text-ink">Trades</h2>
      </div>
      <p className="max-w-2xl text-xs text-ink-mute">
        Every trade recommendation and whether it worked. Each idea stays live until the
        next board that posts the same pair (successor clock). Directional outcomes use
        daily closes only for now — excursion (spike-capture) and level-touch scoring
        follow once the high/low feed lands. Stop / target levels are quoted as published.
      </p>

      <section className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          History — all recommendations
        </h3>
        {history.length === 0 ? (
          <p className="text-sm text-ink-mute">No trade ideas published yet.</p>
        ) : (
          <div className="overflow-x-auto border border-hair">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-hair text-left text-[10px] uppercase tracking-wider text-ink-mute">
                  <th className="px-3 py-2 font-medium">Board</th>
                  <th className="px-3 py-2 font-medium">Pair · bias</th>
                  <th className="px-3 py-2 font-medium">Entry</th>
                  <th className="px-3 py-2 font-medium">Stop · Target</th>
                  <th className="px-3 py-2 font-medium">Lived</th>
                  <th className="px-3 py-2 font-medium">Hold</th>
                  <th className="px-3 py-2 font-medium">Bias</th>
                  <th className="px-3 py-2 font-medium">Levels</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hair">
                {history.map((row) => (
                  <tr key={`${row.runDate}-${row.rank}`}>
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-ink-mute">
                      {row.runDate} · #{row.rank}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-ink">
                      {row.pair} {row.direction}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-mono tabular-nums text-ink">
                      {row.entryBand ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-mono tabular-nums text-ink">
                      {row.stop ?? row.target
                        ? `${row.stop ?? '—'} → ${row.target ?? '—'}`
                        : '—'}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-mono tabular-nums text-ink-mute">
                      {row.sessions ?? '—'}
                      {row.lifecycle === 'live' ? '…' : ''}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 font-mono tabular-nums text-ink">
                      {formatHoldPct(row.holdReturn)}
                      {row.lifecycle === 'live' && row.holdReturn !== null ? '…' : ''}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      <BiasPill row={row} />
                    </td>
                    <td className="whitespace-nowrap px-3 py-2">
                      {row.hasLevels ? <Pill tone="mute">QUOTED</Pill> : <Pill tone="mute">—</Pill>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          Performance — bias (close-based)
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {ideaEval.length > 0 ? (
            <RateCard
              title="Resolved directional win rate"
              subtitle="Among successor-exited ideas; win = signed hold return > 0 (zero counts as loss)"
              primary={formatWilsonPct(ideaSummary.interval)}
              longLabel={formatWilsonPct(ideaSummary.longInterval)}
              shortLabel={formatWilsonPct(ideaSummary.shortInterval)}
            />
          ) : null}
          {ideaEval.length > 0 ? (
            <RateCard
              title="Outcome split"
              subtitle={`Wins ${ideaSummary.winCount} · Losses ${ideaSummary.lossCount} · significant moves ${ideaSummary.significantCount}`}
              primary={`Resolved ${ideaSummary.resolvedCount} · Open ${ideaSummary.openCount} · Missing ${ideaSummary.missingCount}`}
            />
          ) : null}
        </div>
        {ideaEval.length > 0 ? (
          <p className="text-[11px] text-ink-mute">
            Significant move means |hold return| ≥ 0.5 × entry 20d σ (optional overlay on
            the same hold). Missing rates: {ideaSummary.missingCount}.
          </p>
        ) : (
          <p className="text-sm text-ink-mute">No idea eval rows yet.</p>
        )}

        <div className="space-y-2">
          <h4 className="text-[11px] font-medium text-ink-soft">Open ideas</h4>
          {open.length === 0 ? (
            <p className="text-[11px] text-ink-mute">No live ideas.</p>
          ) : (
            <ul className="divide-y divide-hair border border-hair">
              {open.map((row) => (
                <li
                  key={`${row.run_date}-${row.rank}`}
                  className="flex flex-wrap items-baseline justify-between gap-2 px-3 py-2 text-xs"
                >
                  <span className="text-ink">
                    <span className="font-mono text-ink-mute">{row.run_date}</span>
                    {' · '}
                    {row.pair} {row.direction}
                  </span>
                  <span className="font-mono text-[10px] text-ink-mute">open</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          Performance — consensus
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {weightedStab ? (
            <RateCard
              title="Stability (weighted medium)"
              subtitle={
                weightedStab.medianAbsDelta == null
                  ? 'No jumps yet'
                  : `Median |Δscore| ${weightedStab.medianAbsDelta.toFixed(2)} · n=${weightedStab.nJumps}`
              }
              primary={`Sign flip ${formatWilsonPct(weightedStab.signFlipPct)}`}
              longLabel={`|Δ|≥1 ${formatWilsonPct(weightedStab.largeJumpPct)}`}
            />
          ) : null}
          {unweightedStab ? (
            <RateCard
              title="Stability (unweighted)"
              subtitle={
                unweightedStab.medianAbsDelta == null
                  ? 'No jumps yet'
                  : `Median |Δscore| ${unweightedStab.medianAbsDelta.toFixed(2)} · n=${unweightedStab.nJumps}`
              }
              primary={`Sign flip ${formatWilsonPct(unweightedStab.signFlipPct)}`}
              longLabel={`|Δ|≥1 ${formatWilsonPct(unweightedStab.largeJumpPct)}`}
            />
          ) : null}
          <RateCard
            title="5d currency accuracy"
            subtitle="Medium score vs USD-cross move — weaker than pair ideas"
            primary={formatWilsonPct(accuracy.interval)}
            longLabel={`Significant ${formatWilsonPct(accuracy.significantInterval)}`}
            shortLabel={`Open ${accuracy.openCount} · Missing ${accuracy.missingCount}`}
          />
        </div>
      </section>
    </div>
  );
}
