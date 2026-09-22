'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, SegmentedControl } from '@digithings/ui/ui';
import { MultiTimeSeries, type OverlaySeries } from '@digithings/ui';
import { LineChart as LineChartIcon } from 'lucide-react';
import {
  LEAN_BAND,
  SCORE_MAX,
  STRONG_BAND,
  currencyColor,
} from '@/lib/twelve-x/consensus-bar';
import type {
  ConsensusDeltaSet,
  FxBriefRow,
  FxConsensusDivergence,
  FxConsensusSnapshotRow,
  IntelligenceWhy,
} from '@/lib/twelve-x/types';
import { deriveConsensusRows, type ConsensusCurrencyRow } from '@/lib/twelve-x/consensus-view';
import { ConsensusDataTable } from './ConsensusDataTable';
import CurrencyDrilldownPanel from './CurrencyDrilldownPanel';
import DivergencePanel from './DivergencePanel';
import { augmentWithStaleSeries } from '@/lib/twelve-x/consensus-chart';
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
  initialView?: ConsensusView;
}) {
  const { openBrief } = useTwelveX();
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

  const [hiddenCurrencies, setHiddenCurrencies] = useState<Set<string>>(() => new Set());
  const visibleCurrencies = useMemo(
    () => new Set(currencies.filter((currency) => !hiddenCurrencies.has(currency))),
    [currencies, hiddenCurrencies],
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

  const scoreSeries = useMemo<ScoreSeriesRow[]>(
    () => augmentWithStaleSeries(rawScoreSeries, currencies),
    [rawScoreSeries, currencies],
  );

  const hasSeries = scoreSeries.length > 0 && currencies.length > 0;

  // Kit overlay series (Q3b slice 5a, #4443): one solid line per visible
  // currency plus its dashed stale extension. Gaps stay gaps — the old
  // connectNulls bridging is gone deliberately (an interpolated segment is
  // a claim about data that does not exist).
  const overlaySeries = useMemo<OverlaySeries[]>(() => {
    const out: OverlaySeries[] = [];
    for (const c of currencies) {
      if (!visibleCurrencies.has(c)) continue;
      const color = currencyColor(c);
      const live: { t: string; v: number }[] = [];
      const stale: { t: string; v: number }[] = [];
      for (const row of scoreSeries) {
        const v = row[c];
        if (typeof v === 'number' && Number.isFinite(v)) live.push({ t: row.run_date, v });
        const s = row[`${c}__stale`];
        if (typeof s === 'number' && Number.isFinite(s)) stale.push({ t: row.run_date, v: s });
      }
      out.push({ id: c, label: c, points: live, color });
      out.push({ id: `${c}__stale`, label: `${c} (stale)`, points: stale, color, dashed: true });
    }
    return out;
  }, [currencies, scoreSeries, visibleCurrencies]);

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

  const handleLegendClick = (ccy: string) => {
    setHiddenCurrencies((previous) => {
      const next = new Set(previous);
      if (next.has(ccy)) {
        next.delete(ccy);
      } else {
        next.add(ccy);
      }
      return next;
    });
  };

  const handleLegendDoubleClick = (ccy: string) => {
    setHiddenCurrencies(new Set(currencies.filter((currency) => currency !== ccy)));
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <LineChartIcon size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-xl tracking-tight text-ink">G10 consensus</h2>
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
        <div className="space-y-5">
          <Card data-reveal className="gap-0 space-y-3 p-4 md:p-5" data-chart="line">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider">
                Consensus score over time
              </h3>
              <span className="text-[10px] text-ink-mute flex items-center gap-2 w-full">
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2.5 w-3 rounded-none bg-accent/15" />
                  Strong ±{STRONG_BAND}
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block w-3 border-t border-dashed border-accent/60" />
                  Lean ±{LEAN_BAND}
                </span>
                <span className="ml-auto">Raw per-run scores</span>
              </span>
            </div>

            <div className="flex flex-wrap gap-2 py-2" role="group" aria-label="Currency legend">
              {currencies.map((ccy) => {
                const isVisible = visibleCurrencies.has(ccy);
                return (
                  <Button
                    key={ccy}
                    type="button"
                    variant="outline"
                    size="xs"
                    onClick={() => handleLegendClick(ccy)}
                    onDoubleClick={() => handleLegendDoubleClick(ccy)}
                    aria-pressed={isVisible}
                    className={`bg-transparent ${isVisible ? 'border-current opacity-100' : 'border-hair opacity-40'}`}
                    style={{ color: isVisible ? currencyColor(ccy) : undefined }}
                    title={`Click to toggle, double-click to isolate ${ccy}`}
                  >
                    {ccy}
                  </Button>
                );
              })}
            </div>

            {hasSeries ? (
              <div className="w-full">
                <MultiTimeSeries
                  series={overlaySeries}
                  height={360}
                  fmt={(v: number) => v.toFixed(2)}
                  domain={[SCORE_MIN, SCORE_MAX]}
                  references={{
                    bands: [
                      { from: STRONG_BAND, to: SCORE_MAX, tone: 'accent' },
                      { from: SCORE_MIN, to: -STRONG_BAND, tone: 'warn' },
                    ],
                    lines: [
                      { value: STRONG_BAND, tone: 'accent', label: `Strong +${STRONG_BAND}` },
                      { value: LEAN_BAND, tone: 'accent', label: `Lean +${LEAN_BAND}` },
                      { value: 0, tone: 'mute', dashed: false, label: 'Zero' },
                      { value: -LEAN_BAND, tone: 'warn', label: `Lean ${-LEAN_BAND}` },
                      { value: -STRONG_BAND, tone: 'warn', label: `Strong ${-STRONG_BAND}` },
                    ],
                  }}
                  ariaLabel={`G10 consensus score over time, ${SCORE_MIN} (most bearish) to ${SCORE_MAX} (most bullish)`}
                />
              </div>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-ink-mute text-sm">
                Not enough consensus history to chart.
              </div>
            )}
          </Card>
        </div>
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
