'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, CompositionBar, ScoreBar, SegmentedControl, Sparkline } from '@digithings/ui/ui';
import { LineChart as LineChartIcon } from 'lucide-react';
import {
  LEAN_BAND,
  SCORE_MAX,
  STRONG_BAND,
  consensusScoreBarProps,
} from '@/lib/twelve-x/consensus-bar';
import type {
  ConsensusDeltaSet,
  FxBriefRow,
  FxConfluenceSnapshotRow,
  FxConsensusDivergence,
  FxConsensusSnapshotRow,
  IntelligenceWhy,
} from '@/lib/twelve-x/types';
import { deriveConsensusRows, type ConsensusCurrencyRow } from '@/lib/twelve-x/consensus-view';
import { ConsensusDataTable } from './ConsensusDataTable';
import CurrencyDrilldownPanel from './CurrencyDrilldownPanel';
import DivergencePanel from './DivergencePanel';
import { deriveBoardRows, stanceSegments } from '@/lib/twelve-x/board-view';
import { fmtSigned } from '@/lib/twelve-x/format';
import DeltaChip from './DeltaChip';
import { useTwelveX } from './context';

const SCORE_MIN = -SCORE_MAX;

export type ConsensusView = 'table' | 'charts';

export interface ScoreSeriesRow {
  run_date: string;
  [currency: string]: number | string | null;
}

export function pivotScoreSeries(
  series: FxConsensusSnapshotRow[],
  currencies: string[],
): ScoreSeriesRow[] {
  const dates = [...new Set(series.map((r) => r.run_date))].sort((a, b) =>
    a.localeCompare(b),
  );
  const byDate = new Map<string, ScoreSeriesRow>();
  for (const d of dates) byDate.set(d, { run_date: d });

  for (const r of series) {
    const row = byDate.get(r.run_date);
    if (row) row[r.currency] = Number.isFinite(r.score) ? r.score : null;
  }

  return dates.map((d) => byDate.get(d) as ScoreSeriesRow);
}

export default function ConsensusTab({
  series,
  latest,
  latestDate,
  deltas,
  divergenceByCurrency = {},
  focusCcy,
  intelligenceWhy,
  researchBriefs,
  confluence = [],
  initialView = 'table',
}: {
  series: FxConsensusSnapshotRow[];
  latest: FxConsensusSnapshotRow[];
  latestDate: string | null;
  deltas: ConsensusDeltaSet;
  divergenceByCurrency?: Record<string, FxConsensusDivergence>;
  focusCcy?: string | null;
  intelligenceWhy: IntelligenceWhy;
  researchBriefs: FxBriefRow[];
  confluence?: FxConfluenceSnapshotRow[];
  initialView?: ConsensusView;
}) {
  const { crossLink, openBrief } = useTwelveX();
  const [view, setView] = useState<ConsensusView>(initialView);
  const [drilldownCcy, setDrilldownCcy] = useState<string | null>(null);
  const [divergenceCcy, setDivergenceCcy] = useState<string | null>(null);

  const consensusRows = useMemo<ConsensusCurrencyRow[]>(
    () => deriveConsensusRows(series),
    [series],
  );

  const currencies = useMemo<string[]>(
    () => consensusRows.map((r) => r.currency),
    [consensusRows],
  );

  const lastFocusRef = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (focusCcy && focusCcy !== lastFocusRef.current) {
      setDrilldownCcy(focusCcy);
    }
    lastFocusRef.current = focusCcy ?? null;
  }, [focusCcy]);

  const rawScoreSeries = useMemo<ScoreSeriesRow[]>(
    () => pivotScoreSeries(series, currencies),
    [series, currencies],
  );

  const boardRows = useMemo(() => deriveBoardRows(series), [series]);
  const hasSeries = rawScoreSeries.length > 0 && currencies.length > 0;

  const drilldownRow = consensusRows.find((r) => r.currency === drilldownCcy) ?? null;
  const drilldownIntelligence = intelligenceWhy.items.find((item) => item.currency === drilldownCcy) ?? null;
  const divergencePanelItem = divergenceCcy ? divergenceByCurrency[divergenceCcy] ?? null : null;

  const relevantBriefs = useMemo<FxBriefRow[]>(() => {
    if (!drilldownCcy) return [];
    return researchBriefs.filter((brief) => {
      if (!brief.currency_views) return false;
      const views = Array.isArray(brief.currency_views) ? brief.currency_views : [];
      return views.some((view: any) => {
        const ccyInView = view.currency || '';
        const legs = ccyInView.split('/');
        return legs.some((leg: string) => leg.trim().toUpperCase() === drilldownCcy);
      });
    });
  }, [drilldownCcy, researchBriefs]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <LineChartIcon size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-2xl tracking-tight text-ink">G10 consensus</h2>
      </div>

      <p className="text-xs text-ink-mute max-w-2xl">
        Where each G10 currency leans across the desks we track, relevance-weighted and
        followed over time. Scores run {SCORE_MIN} (most bearish) to {SCORE_MAX} (most
        bullish): ±{LEAN_BAND} is a directional lean, ±{STRONG_BAND} strong conviction.
      </p>

      <SegmentedControl
        options={[
          { value: 'table', label: 'Table' },
          { value: 'charts', label: 'Charts' },
        ]}
        value={view}
        onChange={setView}
        dress="accent"
        aria-label="Consensus view"
      />

      {view === 'table' ? (
        <ConsensusDataTable
          series={series}
          latest={latest}
          deltas={deltas}
          divergenceByCurrency={divergenceByCurrency}
          onDivergenceClick={(ccy) => setDivergenceCcy(ccy)}
          onRowClick={(ccy) => setDrilldownCcy(ccy)}
        />
      ) : null}

      {view === 'charts' ? (
        <Card data-reveal className="gap-0 space-y-3 p-4 md:p-5" data-chart="small-multiples">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
              Consensus score over time
            </h3>
            <span className="ml-auto font-mono text-[10px] text-ink-mute">
              raw per-run scores · bar ±{STRONG_BAND} strong, ±{LEAN_BAND} lean
            </span>
          </div>
          {hasSeries ? (
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3" aria-label="Consensus by currency">
              {boardRows.map((r) => {
                const values = rawScoreSeries.map((row) => {
                  const v = row[r.currency];
                  return typeof v === 'number' ? v : null;
                });
                return (
                  <li key={r.currency} data-ccy={r.currency} className="border border-hair p-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="xs"
                      className="mb-1 flex h-auto w-full justify-start gap-2 p-0 font-mono text-[13px] font-semibold text-ink hover:bg-transparent hover:text-accent"
                      title={`${r.currency}: ${r.label} — open drilldown`}
                      onClick={() => setDrilldownCcy(r.currency)}
                    >
                      {r.currency}
                      <span className="font-normal tabular-nums text-ink-soft">{fmtSigned(r.actualNow)}</span>
                      <span className="ml-auto font-normal"><DeltaChip delta={r.priorChange} /></span>
                    </Button>
                    {values.filter((v) => v !== null).length >= 2 ? (
                      <Sparkline
                        values={values}
                        tone="accent"
                        area
                        height={44}
                        preserveAspectRatio="none"
                        className="block h-11 w-full"
                        label={`${r.currency} score over ${values.length} runs`}
                      />
                    ) : (
                      <p className="h-11 font-mono text-[10px] text-ink-mute">Not enough history</p>
                    )}
                    <ScoreBar
                      className="mt-1"
                      label={`${r.currency} latest score`}
                      {...consensusScoreBarProps(r.actualNow)}
                    />
                    <CompositionBar
                      className="mt-1"
                      height={4}
                      segments={stanceSegments(r.stance)}
                      label={`${r.currency} stance mix`}
                    />
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="py-10 text-center text-sm text-ink-mute">
              Not enough consensus history to chart.
            </p>
          )}
        </Card>
      ) : null}

      {/* Confluence reads — where independent desks align on an axis. */}
      {confluence.length > 0 ? (
        <Card data-reveal className="gap-0 space-y-3 p-4 md:p-5">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="font-display text-lg tracking-tight text-ink">Confluence reads</h3>
            <span className="font-mono text-[10px] text-ink-mute">
              {confluence.length}
            </span>
          </div>
          <ul className="grid gap-1">
            {confluence.map((c) => (
              <li
                key={`${c.rank}-${c.currency}`}
                className="flex items-center gap-2 border-t border-hair pt-1 first:border-t-0 first:pt-0"
              >
                <span className="font-mono text-[10px] text-ink-mute">#{c.rank}</span>
                <span className="font-semibold text-ink">{c.currency}</span>
                <span
                  className={`text-xs font-semibold uppercase ${
                    c.direction === 'bullish' || c.direction === 'long'
                      ? 'text-accent'
                      : 'text-warn'
                  }`}
                >
                  {c.direction}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="ml-auto h-auto px-1 py-0 text-[11px] text-ink-soft"
                  onClick={() => crossLink({ kind: 'currency', currency: c.currency })}
                >
                  trend →
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <CurrencyDrilldownPanel
        open={!!drilldownCcy}
        onClose={() => setDrilldownCcy(null)}
        currency={drilldownCcy}
        consensusRow={drilldownRow}
        intelligenceItem={drilldownIntelligence}
        relevantBriefs={relevantBriefs}
        onOpenBrief={openBrief}
      />

      <DivergencePanel
        open={!!divergenceCcy}
        divergence={divergencePanelItem}
        onClose={() => setDivergenceCcy(null)}
      />
    </div>
  );
}
