'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { LineChart as LineChartIcon } from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { consensusAverageSeries, type ScorePoint } from '@/lib/twelve-x/consensus-derive';
import {
  LEAN_BAND,
  SCORE_MAX,
  STRONG_BAND,
  currencyColor,
} from '@/lib/twelve-x/consensus-bar';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import { useChartColors, withAlpha } from '@/lib/chart-colors';
import type { ConsensusDeltaSet, FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import { ConsensusDataTable } from './ConsensusDataTable';
import DeltaChip from './DeltaChip';

/** The bar half-track also represents the min: -SCORE_MAX (max bearish). */
const SCORE_MIN = -SCORE_MAX;

/** Which sub-view of the Consensus page is showing. */
export type ConsensusView = 'table' | 'charts';

/** Line-chart smoothing mode: raw per-run scores, or the consensus average. */
export type SmoothMode = 'raw' | 'ma';

/** One pivoted score row: one entry per run_date, one numeric key per currency. */
export interface ScoreSeriesRow {
  run_date: string;
  [currency: string]: number | string | null;
}

/**
 * Pivot the consensus score time series to one row per run_date, one numeric
 * key per currency — the shape recharts' `<LineChart>` consumes.
 *
 * In `'raw'` mode the value is the per-run raw score (non-finite → `null`, so a
 * gap renders as a break rather than a fabricated `0`). In `'average'` mode the
 * per-currency series is grouped, sorted ascending by `run_date`, reduced to
 * `{score}[]`, smoothed with the shared `consensusAverageSeries(points, 5)`
 * (the trailing-5-run consensus average), then re-pivoted onto the same
 * run_date rows. Switching modes swaps the plotted series.
 */
export function pivotScoreSeries(
  series: FxConsensusSnapshotRow[],
  currencies: string[],
  mode: 'raw' | 'average',
): ScoreSeriesRow[] {
  // Stable ascending run_date axis shared by every currency.
  const dates = [...new Set(series.map((r) => r.run_date))].sort((a, b) =>
    a.localeCompare(b),
  );
  const byDate = new Map<string, ScoreSeriesRow>();
  for (const d of dates) byDate.set(d, { run_date: d });

  if (mode === 'raw') {
    for (const r of series) {
      const row = byDate.get(r.run_date);
      if (row) row[r.currency] = Number.isFinite(r.score) ? r.score : null;
    }
  } else {
    for (const ccy of currencies) {
      // Per-currency points in run_date order → trailing consensus average.
      const points: { date: string; point: ScorePoint }[] = series
        .filter((r) => r.currency === ccy)
        .sort((a, b) => a.run_date.localeCompare(b.run_date))
        .map((r) => ({ date: r.run_date, point: { score: r.score } }));
      const avg = consensusAverageSeries(
        points.map((p) => p.point),
        5,
      );
      points.forEach((p, i) => {
        const row = byDate.get(p.date);
        if (row) row[ccy] = avg[i];
      });
    }
  }

  return dates.map((d) => byDate.get(d) as ScoreSeriesRow);
}

export default function ConsensusTab({
  series,
  latest,
  latestDate,
  onDrillToProvenance,
  deltas,
  focusCcy,
  initialView = 'table',
  initialSmooth = 'raw',
}: {
  series: FxConsensusSnapshotRow[];
  latest: FxConsensusSnapshotRow[];
  latestDate: string | null;
  /** "Why this weight?" cross-link: open Intelligence to that currency's desk provenance. */
  onDrillToProvenance?: (currency: string) => void;
  /** Run-over-run deltas + top movers (timeframe-pinned upstream). */
  deltas: ConsensusDeltaSet;
  /** Cross-link focus: when set, pre-select/highlight this currency. */
  focusCcy?: string | null;
  /** Initial sub-view (Table default). Exposed for deterministic SSR tests. */
  initialView?: ConsensusView;
  /** Initial line-chart smoothing (Raw default). Exposed for SSR tests. */
  initialSmooth?: SmoothMode;
}) {
  const chart = useChartColors();
  const [view, setView] = useState<ConsensusView>(initialView);
  const [smoothMode, setSmoothMode] = useState<SmoothMode>(initialSmooth);

  // Currencies actually present, in canonical G10 order (fall back to any extras).
  const currencies = useMemo<string[]>(() => {
    const present = new Set(series.map((r) => r.currency));
    const ordered: string[] = G10_CURRENCIES.filter((c) => present.has(c));
    const orderedSet = new Set(ordered);
    const extras = [...present].filter((c) => !orderedSet.has(c)).sort();
    return [...ordered, ...extras];
  }, [series]);

  const [selectedCcy, setSelectedCcy] = useState<string | null>(null);

  // Honor a cross-link focus: pre-select/highlight the focused currency. We track
  // the last-applied focus so the user can still override the selection afterward
  // without it snapping back on every re-render.
  const lastFocusRef = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (focusCcy && focusCcy !== lastFocusRef.current) {
      setSelectedCcy(focusCcy);
    }
    lastFocusRef.current = focusCcy ?? null;
  }, [focusCcy]);

  const topMover = deltas.movers[0] ?? null;

  // Pivot the score time series → one row per run_date, one key per currency.
  // Raw shows per-run scores; Average smooths each currency to its trailing
  // consensus average (last 5 runs) before re-pivoting onto the same dates.
  const scoreSeries = useMemo<ScoreSeriesRow[]>(
    () => pivotScoreSeries(series, currencies, smoothMode === 'ma' ? 'average' : 'raw'),
    [series, currencies, smoothMode],
  );

  // Position-split stacked area for the selected (or strongest-conviction) currency.
  const splitFocusCcy = useMemo(() => {
    if (selectedCcy && currencies.includes(selectedCcy)) return selectedCcy;
    // Default: the latest-snapshot currency with the largest |score|.
    let best: string | null = null;
    let bestAbs = -1;
    for (const r of latest) {
      const a = Math.abs(r.score);
      if (a > bestAbs) {
        bestAbs = a;
        best = r.currency;
      }
    }
    return best ?? currencies[0] ?? null;
  }, [selectedCcy, currencies, latest]);

  const splitSeries = useMemo(() => {
    if (!splitFocusCcy) return [];
    return series
      .filter((r) => r.currency === splitFocusCcy)
      .sort((a, b) => a.run_date.localeCompare(b.run_date))
      .map((r) => ({
        run_date: r.run_date,
        bullish: Number(r.bullish_pct ?? 0),
        neutral: Number(r.neutral_pct ?? 0),
        watch: Number(r.watch_pct ?? 0),
        bearish: Number(r.bearish_pct ?? 0),
      }));
  }, [series, splitFocusCcy]);

  const hasSeries = scoreSeries.length > 0 && currencies.length > 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <LineChartIcon size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-2xl tracking-tight text-ink">G10 consensus</h2>
      </div>

      <p className="text-xs text-ink-mute max-w-2xl">
        Relevance-weighted G10 consensus over time. Score ranges {SCORE_MIN} (max bearish) to {SCORE_MAX}{' '}
        (max bullish); bands mark a directional lean (±{LEAN_BAND}) and strong conviction (±{STRONG_BAND}).
      </p>

      {/* Sub-nav: Table | Charts (Table default) */}
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

      {/* Biggest shift since the prior run — shared by both views. */}
      {topMover ? (
        <button
          type="button"
          onClick={() => (onDrillToProvenance ? onDrillToProvenance(topMover.currency) : setSelectedCcy(topMover.currency))}
          className="glass-card flex w-full flex-wrap items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-ink/[0.03]"
          title={
            onDrillToProvenance
              ? `Why this weight? See desk provenance for ${topMover.currency} in Intelligence`
              : `Focus ${topMover.currency}`
          }
        >
          <span className="text-[10px] font-medium uppercase tracking-wide text-ink-mute shrink-0">
            Biggest shift
          </span>
          <span className="font-mono font-semibold shrink-0" style={{ color: currencyColor(topMover.currency) }}>
            {topMover.currency}
          </span>
          <span className="tabular-nums text-xs font-mono text-ink-soft shrink-0">
            {topMover.scoreNow.toFixed(2)}
          </span>
          <DeltaChip delta={topMover.scoreDelta} />
          <span className="ml-auto text-[11px] text-ink-mute max-sm:basis-full max-sm:ml-0">
            {topMover.direction === 'up' ? 'turned more bullish' : 'turned more bearish'} since last run
          </span>
        </button>
      ) : null}

      {/* ===== TABLE VIEW (default, leads the page) ===== */}
      {view === 'table' ? (
        <ConsensusDataTable
          series={series}
          latest={latest}
          deltas={deltas}
          onDrillToProvenance={onDrillToProvenance}
        />
      ) : null}

      {/* ===== CHARTS VIEW ===== */}
      {view === 'charts' ? (
        <div className="space-y-5">
          {/* Currency filter chips — drive both the line highlight and split focus */}
          {currencies.length > 0 ? (
            <div className="flex flex-wrap gap-2" role="group" aria-label="Filter currencies">
              <button
                type="button"
                onClick={() => setSelectedCcy(null)}
                className={`text-[11px] font-medium px-2.5 py-1 rounded-full border transition-colors ${
                  selectedCcy == null
                    ? 'border-accent/40 bg-accent/15 text-accent'
                    : 'border-hair text-ink-mute hover:text-ink'
                }`}
              >
                All
              </button>
              {currencies.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setSelectedCcy(c === selectedCcy ? null : c)}
                  className={`text-[11px] font-mono font-medium px-2.5 py-1 rounded-full border transition-colors ${
                    c === selectedCcy
                      ? 'border-accent/40 bg-accent/15 text-accent'
                      : 'border-hair text-ink-mute hover:text-ink'
                  }`}
                  style={c === selectedCcy ? undefined : { color: currencyColor(c) }}
                >
                  {c}
                </button>
              ))}
            </div>
          ) : null}

          {/* Two-up at ≥1024px; stacked below. */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Score-over-time multi-line chart (Raw | Average) */}
            <div className="glass-card p-4 md:p-5 space-y-3" data-chart="line">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider">
                  Consensus score over time
                </h3>
                {/* Raw | Average smoothing toggle */}
                <div
                  className="inline-flex rounded-lg border border-hair overflow-hidden ml-auto"
                  role="group"
                  aria-label="Smoothing"
                >
                  {(['raw', 'ma'] as const).map((m, idx) => {
                    const on = smoothMode === m;
                    return (
                      <button
                        key={m}
                        type="button"
                        data-smooth={m}
                        aria-pressed={on}
                        onClick={() => setSmoothMode(m)}
                        className={`px-2.5 py-1 text-[11px] font-medium transition-colors ${
                          idx === 0 ? 'border-r border-hair' : ''
                        } ${
                          on
                            ? 'bg-accent/15 text-accent'
                            : 'text-ink-soft hover:text-ink hover:bg-ink/[0.03]'
                        }`}
                      >
                        {m === 'raw' ? 'Raw' : 'Average'}
                      </button>
                    );
                  })}
                </div>
                {/* Band legend: shaded = strong conviction (±1.25); dashed = directional lean (±0.35). */}
                <span className="text-[10px] text-ink-mute flex items-center gap-2 w-full">
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-2.5 w-3 rounded-sm bg-up/15" />
                    Strong ±{STRONG_BAND}
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block w-3 border-t border-dashed border-up/60" />
                    Lean ±{LEAN_BAND}
                  </span>
                  <span className="ml-auto">
                    {smoothMode === 'ma'
                      ? 'Trailing 5-run consensus average'
                      : 'Raw per-run scores'}
                  </span>
                </span>
              </div>
              {hasSeries ? (
                <div className="h-[min(420px,55vh)] min-h-[300px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={scoreSeries} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                      <CartesianGrid stroke={chart.hair} />
                      {/* Strong-conviction bands */}
                      <ReferenceArea y1={STRONG_BAND} y2={SCORE_MAX} fill={chart.up} fillOpacity={0.06} />
                      <ReferenceArea y1={SCORE_MIN} y2={-STRONG_BAND} fill={chart.down} fillOpacity={0.06} />
                      <ReferenceLine y={STRONG_BAND} stroke={chart.up} strokeOpacity={0.5} strokeDasharray="4 4" />
                      <ReferenceLine y={LEAN_BAND} stroke={chart.up} strokeOpacity={0.3} strokeDasharray="2 4" />
                      <ReferenceLine y={0} stroke={withAlpha(chart.ink, 0.25)} />
                      <ReferenceLine y={-LEAN_BAND} stroke={chart.down} strokeOpacity={0.3} strokeDasharray="2 4" />
                      <ReferenceLine y={-STRONG_BAND} stroke={chart.down} strokeOpacity={0.5} strokeDasharray="4 4" />
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
                          // Treat null/undefined explicitly as missing — `Number(null)` is 0,
                          // which would otherwise render a gap in the series as "0.00".
                          const n = val == null ? NaN : typeof val === 'number' ? val : Number(val);
                          return [Number.isNaN(n) ? '—' : n.toFixed(2), String(name)];
                        }}
                      />
                      <Legend formatter={(value: string) => <span className="text-ink-soft text-xs">{value}</span>} />
                      {currencies.map((c) => {
                        const dim = selectedCcy != null && selectedCcy !== c;
                        return (
                          <Line
                            key={c}
                            type="monotone"
                            dataKey={c}
                            name={c}
                            stroke={currencyColor(c)}
                            strokeWidth={selectedCcy === c ? 2.5 : 1.5}
                            strokeOpacity={dim ? 0.18 : 1}
                            dot={false}
                            connectNulls
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

            {/* Position-split stacked area */}
            <div className="glass-card p-4 md:p-5 space-y-3" data-chart="split">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider">
                  Position split over time
                </h3>
                {splitFocusCcy ? (
                  <span
                    className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded"
                    style={{ color: currencyColor(splitFocusCcy) }}
                  >
                    {splitFocusCcy}
                  </span>
                ) : null}
                <span className="text-[11px] text-ink-mute ml-auto">
                  {selectedCcy ? 'Selected currency' : 'Strongest conviction (latest)'}
                </span>
              </div>
              {splitSeries.length > 0 ? (
                <div className="h-[min(320px,45vh)] min-h-[240px] w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={splitSeries} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                      <CartesianGrid stroke={chart.hair} />
                      <XAxis
                        dataKey="run_date"
                        tick={{ fill: chart.axis, fontSize: 11 }}
                        tickFormatter={(d: string) => d?.slice(5)}
                      />
                      <YAxis
                        domain={[0, 100]}
                        tick={{ fill: chart.axis, fontSize: 11 }}
                        tickFormatter={(v) => `${v}%`}
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
                          const n = typeof val === 'number' ? val : Number(val);
                          return [Number.isNaN(n) ? '—' : `${n.toFixed(1)}%`, String(name)];
                        }}
                      />
                      <Legend formatter={(value: string) => <span className="text-ink-soft text-xs">{value}</span>} />
                      <Area type="monotone" dataKey="bullish" stackId="split" name="Bullish" stroke={chart.up} fill={chart.up} fillOpacity={0.6} />
                      <Area type="monotone" dataKey="neutral" stackId="split" name="Neutral" stroke={chart.axis} fill={chart.axis} fillOpacity={0.45} />
                      <Area type="monotone" dataKey="watch" stackId="split" name="Watch" stroke={chart.warn} fill={chart.warn} fillOpacity={0.5} />
                      <Area type="monotone" dataKey="bearish" stackId="split" name="Bearish" stroke={chart.down} fill={chart.down} fillOpacity={0.6} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-[240px] flex items-center justify-center text-ink-mute text-sm">
                  No position-split history for this currency.
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
