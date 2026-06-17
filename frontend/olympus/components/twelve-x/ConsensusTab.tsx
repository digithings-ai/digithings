'use client';

import { useMemo, useState } from 'react';
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
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { FxConsensusSnapshotRow } from '@/lib/twelve-x/types';

/** Score thresholds (shared with twelve-x): |score| ≥ 1.25 = strong, ≥ 0.35 = lean. */
const STRONG_BAND = 1.25;
const LEAN_BAND = 0.35;
const SCORE_MIN = -2;
const SCORE_MAX = 2;

/** Stable per-currency colors (G10 order). */
const CURRENCY_COLORS: Record<string, string> = {
  USD: '#3B82F6',
  EUR: '#10B981',
  JPY: '#F59E0B',
  GBP: '#EF4444',
  CHF: '#8B5CF6',
  CAD: '#06B6D4',
  AUD: '#F97316',
  NZD: '#EC4899',
  SEK: '#6366F1',
  NOK: '#14B8A6',
};

function currencyColor(ccy: string): string {
  return CURRENCY_COLORS[ccy] ?? '#94a3b8';
}

/** score → .fin-* text color (strong/lean bands). */
function scoreColorClass(score: number): string {
  if (score >= LEAN_BAND) return 'text-fin-green';
  if (score <= -LEAN_BAND) return 'text-fin-red';
  return 'text-text-secondary';
}

function scoreLabel(score: number): string {
  if (score >= STRONG_BAND) return 'Strong bull';
  if (score >= LEAN_BAND) return 'Bullish lean';
  if (score <= -STRONG_BAND) return 'Strong bear';
  if (score <= -LEAN_BAND) return 'Bearish lean';
  return 'Neutral';
}

interface ScoreSeriesRow {
  run_date: string;
  [currency: string]: number | string | null;
}

export default function ConsensusTab({
  series,
  latest,
  latestDate,
}: {
  series: FxConsensusSnapshotRow[];
  latest: FxConsensusSnapshotRow[];
  latestDate: string | null;
}) {
  // Currencies actually present, in canonical G10 order (fall back to any extras).
  const currencies = useMemo<string[]>(() => {
    const present = new Set(series.map((r) => r.currency));
    const ordered: string[] = G10_CURRENCIES.filter((c) => present.has(c));
    const orderedSet = new Set(ordered);
    const extras = [...present].filter((c) => !orderedSet.has(c)).sort();
    return [...ordered, ...extras];
  }, [series]);

  const [selectedCcy, setSelectedCcy] = useState<string | null>(null);

  // Pivot the score time series → one row per run_date, one key per currency.
  const scoreSeries = useMemo<ScoreSeriesRow[]>(() => {
    const byDate = new Map<string, ScoreSeriesRow>();
    for (const r of series) {
      let row = byDate.get(r.run_date);
      if (!row) {
        row = { run_date: r.run_date };
        byDate.set(r.run_date, row);
      }
      row[r.currency] = Number.isFinite(r.score) ? r.score : null;
    }
    return [...byDate.values()].sort((a, b) => a.run_date.localeCompare(b.run_date));
  }, [series]);

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

  const latestSorted = useMemo(
    () => [...latest].sort((a, b) => b.score - a.score),
    [latest]
  );

  const hasSeries = scoreSeries.length > 0 && currencies.length > 0;

  return (
    <div className="space-y-5">
      <p className="text-xs text-text-muted max-w-2xl">
        Relevance-weighted G10 consensus over time. Score ranges {SCORE_MIN} (max bearish) to {SCORE_MAX}{' '}
        (max bullish); bands mark a directional lean (±{LEAN_BAND}) and strong conviction (±{STRONG_BAND}).
      </p>

      {/* Currency filter chips — toggles the focused currency for the split chart */}
      {currencies.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setSelectedCcy(null)}
            className={`text-[11px] font-medium px-2.5 py-1 rounded-full border transition-colors ${
              selectedCcy == null
                ? 'border-fin-blue/40 bg-fin-blue/15 text-fin-blue'
                : 'border-border-subtle text-text-muted hover:text-text-primary'
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
                  ? 'border-fin-blue/40 bg-fin-blue/15 text-fin-blue'
                  : 'border-border-subtle text-text-muted hover:text-text-primary'
              }`}
              style={c === selectedCcy ? undefined : { color: currencyColor(c) }}
            >
              {c}
            </button>
          ))}
        </div>
      ) : null}

      {/* Score-over-time multi-line chart */}
      <div className="glass-card p-4 md:p-5 space-y-3">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          Consensus score over time
        </h3>
        {hasSeries ? (
          <div className="h-[min(420px,55vh)] min-h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={scoreSeries} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                {/* Strong-conviction bands */}
                <ReferenceArea y1={STRONG_BAND} y2={SCORE_MAX} fill="#3fb984" fillOpacity={0.06} />
                <ReferenceArea y1={SCORE_MIN} y2={-STRONG_BAND} fill="#e0654b" fillOpacity={0.06} />
                <ReferenceLine y={STRONG_BAND} stroke="#3fb984" strokeOpacity={0.5} strokeDasharray="4 4" />
                <ReferenceLine y={LEAN_BAND} stroke="#3fb984" strokeOpacity={0.3} strokeDasharray="2 4" />
                <ReferenceLine y={0} stroke="rgba(255,255,255,0.25)" />
                <ReferenceLine y={-LEAN_BAND} stroke="#e0654b" strokeOpacity={0.3} strokeDasharray="2 4" />
                <ReferenceLine y={-STRONG_BAND} stroke="#e0654b" strokeOpacity={0.5} strokeDasharray="4 4" />
                <XAxis
                  dataKey="run_date"
                  tick={{ fill: '#71717a', fontSize: 11 }}
                  tickFormatter={(d: string) => d?.slice(5)}
                />
                <YAxis
                  domain={[SCORE_MIN, SCORE_MAX]}
                  ticks={[-2, -1.25, -0.35, 0, 0.35, 1.25, 2]}
                  tick={{ fill: '#71717a', fontSize: 11 }}
                  width={44}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--color-bg-secondary)',
                    border: '1px solid var(--color-border-subtle)',
                    color: 'var(--color-text-primary)',
                    borderRadius: '8px',
                    fontSize: '0.8rem',
                  }}
                  formatter={(val, name) => {
                    const n = typeof val === 'number' ? val : Number(val);
                    return [Number.isNaN(n) ? '—' : n.toFixed(2), String(name)];
                  }}
                />
                <Legend formatter={(value: string) => <span className="text-text-secondary text-xs">{value}</span>} />
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
          <div className="h-[300px] flex items-center justify-center text-text-muted text-sm">
            Not enough consensus history to chart.
          </div>
        )}
      </div>

      {/* Position-split stacked area */}
      <div className="glass-card p-4 md:p-5 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
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
          <span className="text-[11px] text-text-muted ml-auto">
            {selectedCcy ? 'Selected currency' : 'Strongest conviction (latest)'}
          </span>
        </div>
        {splitSeries.length > 0 ? (
          <div className="h-[min(320px,45vh)] min-h-[240px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={splitSeries} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                <XAxis
                  dataKey="run_date"
                  tick={{ fill: '#71717a', fontSize: 11 }}
                  tickFormatter={(d: string) => d?.slice(5)}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: '#71717a', fontSize: 11 }}
                  tickFormatter={(v) => `${v}%`}
                  width={44}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--color-bg-secondary)',
                    border: '1px solid var(--color-border-subtle)',
                    color: 'var(--color-text-primary)',
                    borderRadius: '8px',
                    fontSize: '0.8rem',
                  }}
                  formatter={(val, name) => {
                    const n = typeof val === 'number' ? val : Number(val);
                    return [Number.isNaN(n) ? '—' : `${n.toFixed(1)}%`, String(name)];
                  }}
                />
                <Legend formatter={(value: string) => <span className="text-text-secondary text-xs">{value}</span>} />
                <Area type="monotone" dataKey="bullish" stackId="split" name="Bullish" stroke="#3fb984" fill="#3fb984" fillOpacity={0.6} />
                <Area type="monotone" dataKey="neutral" stackId="split" name="Neutral" stroke="#94a3b8" fill="#94a3b8" fillOpacity={0.45} />
                <Area type="monotone" dataKey="watch" stackId="split" name="Watch" stroke="#e0b341" fill="#e0b341" fillOpacity={0.5} />
                <Area type="monotone" dataKey="bearish" stackId="split" name="Bearish" stroke="#e0654b" fill="#e0654b" fillOpacity={0.6} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-[240px] flex items-center justify-center text-text-muted text-sm">
            No position-split history for this currency.
          </div>
        )}
      </div>

      {/* Latest-snapshot table */}
      <div className="glass-card p-0 overflow-hidden">
        <div className="px-5 py-3 bg-bg-secondary border-b border-border-subtle flex items-center gap-3">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">Latest consensus</h3>
          {latestDate ? (
            <span className="text-[10px] font-mono text-text-muted ml-auto">{latestDate}</span>
          ) : null}
        </div>
        {latestSorted.length > 0 ? (
          <ConsensusTable rows={latestSorted} />
        ) : (
          <div className="p-8 text-center text-text-muted text-sm">No latest consensus snapshot available.</div>
        )}
      </div>
    </div>
  );
}

function ConsensusTable({ rows }: { rows: FxConsensusSnapshotRow[] }) {
  return (
    <div className="overflow-x-auto">
      {/* Header */}
      <div
        className="grid items-center gap-2 px-5 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted border-b border-border-subtle min-w-[680px]"
        style={{ gridTemplateColumns: '64px 1fr 96px 88px 88px 64px 64px' }}
      >
        <span>Ccy</span>
        <span>Score</span>
        <span className="text-right">Signal</span>
        <span className="text-right">Confidence</span>
        <span className="text-right">Agreement</span>
        <span className="text-right">Views</span>
        <span className="text-right">Brokers</span>
      </div>
      <div className="divide-y divide-border-subtle">
        {rows.map((r) => {
          const colorClass = scoreColorClass(r.score);
          // Normalize score [-2,2] → bar width fraction of the half-track.
          const frac = Math.min(1, Math.abs(r.score) / SCORE_MAX);
          const bullish = r.score >= 0;
          return (
            <div
              key={`${r.run_date}-${r.currency}`}
              className="grid items-center gap-2 px-5 py-3 text-sm min-w-[680px] hover:bg-white/[0.02] transition-colors"
              style={{ gridTemplateColumns: '64px 1fr 96px 88px 88px 64px 64px' }}
            >
              <span className="font-mono font-semibold" style={{ color: currencyColor(r.currency) }}>
                {r.currency}
              </span>
              {/* Score bar: centered zero, fills right (bull) / left (bear) */}
              <div className="flex items-center gap-2">
                <div className="relative h-2 flex-1 rounded-full bg-white/[0.05] overflow-hidden">
                  <div className="absolute inset-y-0 left-1/2 w-px bg-white/20" />
                  <div
                    className={`absolute inset-y-0 ${bullish ? 'left-1/2' : 'right-1/2'} ${
                      bullish ? 'bg-fin-green' : 'bg-fin-red'
                    }`}
                    style={{ width: `${frac * 50}%` }}
                  />
                </div>
                <span className={`qn-metric tabular-nums w-12 text-right shrink-0 ${colorClass}`}>
                  {Number.isFinite(r.score) ? r.score.toFixed(2) : '—'}
                </span>
              </div>
              <span className={`text-right text-xs font-medium ${colorClass}`}>{scoreLabel(r.score)}</span>
              <span className="text-right tabular-nums text-text-secondary">
                {Number.isFinite(r.confidence) ? `${(r.confidence * 100).toFixed(0)}%` : '—'}
              </span>
              <span className="text-right tabular-nums text-text-secondary">
                {Number.isFinite(r.agreement) ? `${(r.agreement * 100).toFixed(0)}%` : '—'}
              </span>
              <span className="text-right tabular-nums text-text-muted">{r.n_views ?? '—'}</span>
              <span className="text-right tabular-nums text-text-muted">{r.n_brokers ?? '—'}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
