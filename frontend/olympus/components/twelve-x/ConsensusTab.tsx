'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { LineChart as LineChartIcon } from 'lucide-react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  LEAN_BAND,
  SCORE_MAX,
  STRONG_BAND,
  currencyColor,
} from '@/lib/twelve-x/consensus-bar';
import { useChartColors, withAlpha } from '@/lib/chart-colors';
import type { ConsensusDeltaSet, FxConsensusSnapshotRow, FxBriefRow, IntelligenceWhy } from '@/lib/twelve-x/types';
import { deriveConsensusRows, type ConsensusCurrencyRow } from '@/lib/twelve-x/consensus-view';
import { ConsensusDataTable } from './ConsensusDataTable';
import CurrencyDrilldownPanel from './CurrencyDrilldownPanel';
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
  focusCcy,
  intelligenceWhy,
  researchBriefs,
  initialView = 'table',
}: {
  series: FxConsensusSnapshotRow[];
  latest: FxConsensusSnapshotRow[];
  latestDate: string | null;
  deltas: ConsensusDeltaSet;
  focusCcy?: string | null;
  intelligenceWhy: IntelligenceWhy;
  researchBriefs: FxBriefRow[];
  initialView?: ConsensusView;
}) {
  const chart = useChartColors();
  const { openBrief } = useTwelveX();
  const [view, setView] = useState<ConsensusView>(initialView);
  const [drilldownCcy, setDrilldownCcy] = useState<string | null>(null);

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

  const drilldownRow = consensusRows.find((r) => r.currency === drilldownCcy) ?? null;
  const drilldownIntelligence = intelligenceWhy.items.find((item) => item.currency === drilldownCcy) ?? null;

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
        <h2 className="font-display text-2xl tracking-tight text-ink">G10 consensus</h2>
      </div>

      <p className="text-xs text-ink-mute max-w-2xl">
        Where each G10 currency leans across the desks we track, relevance-weighted and
        followed over time. Scores run {SCORE_MIN} (most bearish) to {SCORE_MAX} (most
        bullish): ±{LEAN_BAND} is a directional lean, ±{STRONG_BAND} strong conviction.
      </p>

      <div
        className="inline-flex rounded-lg border border-hair overflow-hidden"
        role="group"
        aria-label="Consensus view"
      >
        {(['table', 'charts'] as const).map((v, idx) => {
          const on = view === v;
          return (
            <button
              key={v}
              type="button"
              data-conview={v}
              aria-pressed={on}
              onClick={() => setView(v)}
              className={`px-3.5 py-1.5 text-[11.5px] font-medium capitalize transition-colors ${
                idx === 0 ? 'border-r border-hair' : ''
              } ${
                on
                  ? 'bg-accent/15 text-accent'
                  : 'text-ink-soft hover:text-ink hover:bg-ink/[0.03]'
              }`}
            >
              {v === 'table' ? 'Table' : 'Charts'}
            </button>
          );
        })}
      </div>

      {view === 'table' ? (
        <ConsensusDataTable
          series={series}
          latest={latest}
          deltas={deltas}
          onRowClick={(ccy) => setDrilldownCcy(ccy)}
        />
      ) : null}

      {view === 'charts' ? (
        <div className="space-y-5">
          <div className="glass-card p-4 md:p-5 space-y-3" data-chart="line">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider">
                Consensus score over time
              </h3>
              <span className="text-[10px] text-ink-mute flex items-center gap-2 w-full">
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2.5 w-3 rounded-sm bg-accent/15" />
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
                  <button
                    key={ccy}
                    type="button"
                    onClick={() => handleLegendClick(ccy)}
                    onDoubleClick={() => handleLegendDoubleClick(ccy)}
                    aria-pressed={isVisible}
                    className={`px-2.5 py-1 text-xs font-medium rounded border transition-colors ${
                      isVisible
                        ? 'border-current opacity-100'
                        : 'border-hair opacity-40'
                    }`}
                    style={{ color: isVisible ? currencyColor(ccy) : undefined }}
                    title={`Click to toggle, double-click to isolate ${ccy}`}
                  >
                    {ccy}
                  </button>
                );
              })}
            </div>

            {hasSeries ? (
              <div className="h-[min(420px,55vh)] min-h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={scoreSeries} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                    <CartesianGrid stroke={chart.hair} />
                    <ReferenceArea y1={STRONG_BAND} y2={SCORE_MAX} fill={chart.accent} fillOpacity={0.06} />
                    <ReferenceArea y1={SCORE_MIN} y2={-STRONG_BAND} fill={chart.warn} fillOpacity={0.06} />
                    <ReferenceLine y={STRONG_BAND} stroke={chart.accent} strokeOpacity={0.5} strokeDasharray="4 4" />
                    <ReferenceLine y={LEAN_BAND} stroke={chart.accent} strokeOpacity={0.3} strokeDasharray="2 4" />
                    <ReferenceLine y={0} stroke={withAlpha(chart.ink, 0.25)} />
                    <ReferenceLine y={-LEAN_BAND} stroke={chart.warn} strokeOpacity={0.3} strokeDasharray="2 4" />
                    <ReferenceLine y={-STRONG_BAND} stroke={chart.warn} strokeOpacity={0.5} strokeDasharray="4 4" />
                    <XAxis
                      dataKey="run_date"
                      tick={{ fill: chart.axis, fontSize: 11 }}
                      tickFormatter={(d: string) => d?.slice(5)}
                      label={{ value: 'Run date', position: 'insideBottom', offset: -4, fill: chart.axis, fontSize: 10 }}
                    />
                    <YAxis
                      domain={[SCORE_MIN, SCORE_MAX]}
                      ticks={[-2, -1.25, -0.35, 0, 0.35, 1.25, 2]}
                      tick={{ fill: chart.axis, fontSize: 11 }}
                      width={44}
                    />
                    <Tooltip
                      contentStyle={{
                        background: 'var(--term-bg)',
                        border: '1px solid var(--hair)',
                        color: 'var(--ink)',
                        borderRadius: '8px',
                        fontSize: '0.8rem',
                      }}
                      formatter={(val, name) => {
                        const n = val == null ? NaN : typeof val === 'number' ? val : Number(val);
                        return [Number.isNaN(n) ? '—' : n.toFixed(2), String(name)];
                      }}
                    />
                    {currencies.map((c) => {
                      const isVisible = visibleCurrencies.has(c);
                      if (!isVisible) return null;
                      return (
                        <Line
                          key={c}
                          type="monotone"
                          dataKey={c}
                          name={c}
                          stroke={currencyColor(c)}
                          strokeWidth={1.5}
                          dot={false}
                          connectNulls
                        />
                      );
                    })}
                    {currencies.map((c) => {
                      const isVisible = visibleCurrencies.has(c);
                      if (!isVisible) return null;
                      return (
                        <Line
                          key={`${c}__stale`}
                          type="monotone"
                          dataKey={`${c}__stale`}
                          stroke={currencyColor(c)}
                          strokeWidth={1.5}
                          strokeDasharray="3 3"
                          dot={false}
                          connectNulls
                          legendType="none"
                        />
                      );
                    })}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-ink-mute text-sm">
                Not enough consensus history to chart.
              </div>
            )}
          </div>
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
    </div>
  );
}
