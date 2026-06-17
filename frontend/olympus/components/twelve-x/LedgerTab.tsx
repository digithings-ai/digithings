'use client';

import { useMemo, useState } from 'react';
import { ScrollText } from 'lucide-react';

import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { FxLedgerRow } from '@/lib/twelve-x/types';

/** Classification → badge styling (.fin-* tokens) for the lifecycle state. */
function classificationBadge(classification: string): { text: string; bg: string; border: string } {
  const c = classification.trim().toLowerCase();
  if (c === 'active') return { text: 'text-fin-blue', bg: 'bg-fin-blue/10', border: 'border-fin-blue/30' };
  if (c === 'confirmed') return { text: 'text-fin-green', bg: 'bg-fin-green/10', border: 'border-fin-green/30' };
  if (c === 'invalidated') return { text: 'text-fin-red', bg: 'bg-fin-red/10', border: 'border-fin-red/30' };
  if (c === 'superseded') return { text: 'text-fin-amber', bg: 'bg-fin-amber/10', border: 'border-fin-amber/30' };
  return { text: 'text-text-secondary', bg: 'bg-white/[0.04]', border: 'border-border-subtle' };
}

function classificationLabel(classification: string): string {
  const c = classification.trim();
  if (!c) return '—';
  return c.charAt(0).toUpperCase() + c.slice(1).toLowerCase();
}

/** Direction → .fin-* text color. */
function directionColorClass(direction: string): string {
  const d = direction.trim().toLowerCase();
  if (d === 'bullish' || d === 'long' || d === 'buy') return 'text-fin-green';
  if (d === 'bearish' || d === 'short' || d === 'sell') return 'text-fin-red';
  if (d === 'watch') return 'text-fin-amber';
  return 'text-text-secondary';
}

/** The three relevance-weight factors, in stacked-bar order. */
const WEIGHT_SEGMENTS = [
  { key: 'w_time' as const, label: 'Time', color: '#3B82F6' },
  { key: 'w_event' as const, label: 'Event', color: '#10B981' },
  { key: 'w_review' as const, label: 'Review', color: '#8B5CF6' },
];

function safeNum(v: number): number {
  return Number.isFinite(v) ? v : 0;
}

/** Stacked w_time·w_event·w_review bar (CSS, no recharts) sized by each factor.
 *
 * When the three factors are equal (the common case while the relevance review is
 * un-differentiated — every desk currently scores 1·1·1), a proportional bar would
 * draw three identical thirds that imply a breakdown that isn't there. In that case
 * we render a flat single bar + a "uniform" tag so the visual is honest; only when
 * the factors actually differ do we draw the proportional stack. */
function WeightBar({ row }: { row: FxLedgerRow }) {
  const segments = WEIGHT_SEGMENTS.map((s) => ({ ...s, value: Math.max(0, safeNum(row[s.key])) }));
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const uniform =
    segments.length > 0 && segments.every((s) => Math.abs(s.value - segments[0].value) < 1e-9);

  return (
    <div className="space-y-1">
      <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-white/[0.05]">
        {total > 0 && !uniform
          ? segments.map((s) =>
              s.value > 0 ? (
                <div
                  key={s.key}
                  className="h-full first:rounded-l-full last:rounded-r-full"
                  style={{ width: `${(s.value / total) * 100}%`, backgroundColor: s.color }}
                  title={`${s.label}: ${s.value.toFixed(2)}`}
                />
              ) : null
            )
          : total > 0 ? (
              <div className="h-full w-full rounded-full bg-white/15" title="time · event · review weights are uniform" />
            ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5">
        {segments.map((s) => (
          <span key={s.key} className="flex items-center gap-1 text-[10px] text-text-muted">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ backgroundColor: uniform ? 'rgba(255,255,255,0.2)' : s.color }}
            />
            {s.label}
            <span className="tabular-nums text-text-secondary">{s.value.toFixed(2)}</span>
          </span>
        ))}
        {uniform ? <span className="text-[10px] text-text-muted/70">uniform</span> : null}
      </div>
    </div>
  );
}

export default function LedgerTab({
  rows,
  runDate,
  runDates,
  onSelectRun,
  ccy,
  onOpenBrief,
}: {
  rows: FxLedgerRow[];
  runDate: string | null;
  runDates: string[];
  onSelectRun: (runDate: string) => void;
  // A "why this weight?" drill from a consensus cell pre-filters the ledger to this
  // currency (owned by the parent so it survives tab switches; no URL coupling).
  ccy: string | null;
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
  const [classFilter, setClassFilter] = useState<string>('all');
  const [ccyFilter, setCcyFilter] = useState<string>(ccy ?? 'all');

  // Re-apply the currency filter whenever the drill-down currency changes. Adjusting
  // state during render (rather than in an effect) avoids an extra commit + the
  // cascading-render lint — see https://react.dev/learn/you-might-not-need-an-effect.
  const [lastCcy, setLastCcy] = useState<string | null>(ccy);
  if (ccy && ccy !== lastCcy) {
    setLastCcy(ccy);
    setCcyFilter(ccy);
  }

  // Distinct classifications / currencies present, for the filter chips.
  const classifications = useMemo(
    () => [...new Set(rows.map((r) => r.classification).filter(Boolean))].sort(),
    [rows]
  );
  const currencies = useMemo<string[]>(() => {
    const present = new Set(rows.map((r) => r.currency));
    const ordered = G10_CURRENCIES.filter((c) => present.has(c));
    const orderedSet = new Set<string>(ordered);
    const extras = [...present].filter((c) => !orderedSet.has(c)).sort();
    return [...ordered, ...extras];
  }, [rows]);

  const filtered = useMemo(
    () =>
      rows.filter(
        (r) =>
          (classFilter === 'all' || r.classification === classFilter) &&
          (ccyFilter === 'all' || r.currency === ccyFilter)
      ),
    [rows, classFilter, ccyFilter]
  );

  const gridCols = '120px 64px 72px 1fr 110px 72px';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <ScrollText size={18} className="shrink-0 text-fin-blue" aria-hidden />
        <h2 className="text-base font-semibold text-text-primary md:text-lg">Relevance ledger</h2>
        {/* Run picker */}
        {runDates.length > 0 ? (
          <label className="ml-auto flex items-center gap-2 text-[11px] text-text-muted">
            Run
            <select
              value={runDate ?? ''}
              onChange={(e) => onSelectRun(e.target.value)}
              className="rounded-md border border-border-subtle bg-bg-secondary px-2 py-1 font-mono text-[11px] text-text-secondary focus:border-fin-blue/50 focus:outline-none"
            >
              {runDates.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        ) : runDate ? (
          <span className="ml-auto font-mono text-[10px] text-text-muted">{runDate}</span>
        ) : null}
      </div>

      <p className="max-w-2xl px-1 text-xs text-text-muted">
        The deliberation behind the consensus: every desk opinion that fed the run, its lifecycle
        state, the relevance weight it earned, and the time·event·review decomposition of that
        weight. Each row links to its source brief.
      </p>

      {/* Filters */}
      {rows.length > 0 ? (
        <div className="flex flex-col gap-2 px-1">
          {classifications.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">State</span>
              <FilterChip active={classFilter === 'all'} onClick={() => setClassFilter('all')}>
                All
              </FilterChip>
              {classifications.map((c) => (
                <FilterChip key={c} active={classFilter === c} onClick={() => setClassFilter(c)}>
                  {classificationLabel(c)}
                </FilterChip>
              ))}
            </div>
          ) : null}
          {currencies.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">Ccy</span>
              <FilterChip active={ccyFilter === 'all'} onClick={() => setCcyFilter('all')}>
                All
              </FilterChip>
              {currencies.map((c) => (
                <FilterChip key={c} mono active={ccyFilter === c} onClick={() => setCcyFilter(c)}>
                  {c}
                </FilterChip>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {filtered.length > 0 ? (
        <div className="glass-card overflow-hidden p-0">
          <div className="overflow-x-auto">
            {/* Header */}
            <div
              className="grid min-w-[760px] items-center gap-3 border-b border-border-subtle bg-bg-secondary px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted"
              style={{ gridTemplateColumns: gridCols }}
            >
              <span>Desk</span>
              <span>Ccy</span>
              <span>Dir</span>
              <span>Weight (time · event · review)</span>
              <span>State</span>
              <span className="text-right">Relevance</span>
            </div>
            <div className="divide-y divide-border-subtle">
              {filtered.map((r) => {
                const badge = classificationBadge(r.classification);
                return (
                  <div
                    key={`${r.source_file}-${r.view_index}`}
                    className="grid min-w-[760px] items-center gap-3 px-4 py-3 text-sm transition-colors hover:bg-white/[0.02]"
                    style={{ gridTemplateColumns: gridCols }}
                  >
                    {/* Desk → drill to brief */}
                    <button
                      type="button"
                      onClick={() => onOpenBrief(r.source_file, r.run_date)}
                      className="truncate text-left font-medium text-text-primary hover:text-fin-blue hover:underline"
                      title={`${r.broker_name ?? 'Unknown desk'} — why this weight? open brief ${r.source_file}`}
                    >
                      {r.broker_name ?? 'Unknown'}
                    </button>
                    <span className="font-mono text-text-secondary">{r.currency}</span>
                    <span className={`text-xs font-medium ${directionColorClass(r.direction)}`}>
                      {r.direction || '—'}
                    </span>
                    <div className="min-w-0">
                      <WeightBar row={r} />
                      {r.reason ? (
                        <p className="mt-1 truncate text-[11px] text-text-muted" title={r.reason}>
                          {r.reason}
                        </p>
                      ) : null}
                    </div>
                    <span
                      className={`inline-flex w-fit items-center rounded-full border px-2 py-0.5 text-[10px] font-medium ${badge.text} ${badge.bg} ${badge.border}`}
                    >
                      {classificationLabel(r.classification)}
                    </span>
                    <span className="qn-metric text-right tabular-nums text-text-primary">
                      {Number.isFinite(r.relevance) ? r.relevance.toFixed(2) : '—'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        <div className="glass-card p-10 text-center text-sm text-text-muted">
          {rows.length > 0
            ? 'No ledger rows match the current filters.'
            : `No relevance ledger rows${runDate ? ` for ${runDate}` : ''} yet.`}
        </div>
      )}
    </div>
  );
}

function FilterChip({
  active,
  mono,
  onClick,
  children,
}: {
  active: boolean;
  mono?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
        mono ? 'font-mono' : ''
      } ${
        active
          ? 'border-fin-blue/40 bg-fin-blue/15 text-fin-blue'
          : 'border-border-subtle text-text-muted hover:text-text-primary'
      }`}
    >
      {children}
    </button>
  );
}
