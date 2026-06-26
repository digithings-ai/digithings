'use client';

import { Fragment, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import { pnlColor } from '@/components/ui';
import type { DashboardPositionEvent, PositionHistoryRow, Thesis } from '@/lib/types';
import type { BookReconciliation, ReconciledPosition } from '@/lib/book-reconciliation';
import type { TableRow } from '@/lib/database.types';
import PositionDrilldown from '@/components/portfolio/PositionDrilldown';
import RiskEnvelopeCell from '@/components/portfolio/RiskEnvelopeCell';
import { ConvictionMeter } from '@/components/shared/conviction-meter';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { normalizeThesisId } from '@/lib/thesis-id';

function thesisNames(ids: string[], thesisById: Map<string, Thesis>): string {
  if (!ids.length) return '—';
  return ids.map((id) => thesisById.get(normalizeThesisId(id))?.name ?? id).join(', ');
}

export default function AllocationsPositionsTable(props: {
  reconciliation: BookReconciliation;
  positionHistory: PositionHistoryRow[];
  positionEvents: DashboardPositionEvent[];
  thesisById: Map<string, Thesis>;
  lastUpdated: string | null;
  decisionByTicker: Map<string, TableRow<'decision_log'>>;
}) {
  const { reconciliation, positionHistory, positionEvents, thesisById, lastUpdated, decisionByTicker } =
    props;
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  // Conviction-first within each sector; ties broken by normalized weight.
  const sorted = useMemo(
    () =>
      [...reconciliation.rows].sort(
        (a, b) => (b.conviction ?? 0) - (a.conviction ?? 0) || b.normalizedWeight - a.normalizedWeight
      ),
    [reconciliation.rows]
  );

  const inactive = useMemo<ReconciledPosition[]>(() => {
    if (!showInactive) return [];
    const active = new Set(sorted.map((p) => p.ticker));
    const lastByTicker = new Map<string, PositionHistoryRow>();
    for (const r of positionHistory) {
      const t = String(r.ticker || '').toUpperCase();
      if (!t || active.has(t)) continue;
      const prev = lastByTicker.get(t);
      if (!prev || r.date > prev.date) lastByTicker.set(t, r);
    }
    return [...lastByTicker.values()]
      .map((r) => {
        const t = String(r.ticker).toUpperCase();
        const tid = r.thesis_id ? String(r.thesis_id) : null;
        const p: ReconciledPosition = {
          ticker: t,
          name: 'Former position',
          type: 'LONG',
          weight_actual: 0,
          weight_target: null,
          weight_delta: null,
          current_price: null,
          entry_price: null,
          entry_date: null,
          rationale: '',
          thesis_ids: tid ? [tid] : [],
          category: r.category ?? 'uncategorized',
          pm_notes: '',
          stats: {},
          normalizedWeight: 0,
          conviction: null,
          stop_loss_pct: null,
          target_pct_gain: null,
          horizon_days: null,
          sector_bucket: null,
        };
        return p;
      })
      .sort((a, b) => a.ticker.localeCompare(b.ticker));
  }, [positionHistory, showInactive, sorted]);

  const allRows = useMemo<ReconciledPosition[]>(() => [...sorted, ...inactive], [sorted, inactive]);

  const maxWeight = sorted.length ? Math.max(...sorted.map((p) => p.normalizedWeight)) : 0;

  // Show the Target column only when at least one position has a target weight set.
  // (WS1 populates weight_target from the pm-rebalance recommended book; it will be
  //  null for every row in portfolios that haven't run through the PM rebalance node.)
  const hasTargets = useMemo(() => sorted.some((p) => p.weight_target != null), [sorted]);

  // Exact <th> count: Ticker, Weight, Conviction, Day, Unrealized, Risk, Thesis, Decision, chevron
  // = 9; with targets add Target + Δ = 11.
  const colCount = hasTargets ? 11 : 9;

  // Group active+inactive rows by sector, heaviest sector first.
  const grouped = useMemo(() => {
    const m = new Map<string, ReconciledPosition[]>();
    for (const p of allRows) {
      const key = p.sector_bucket ?? 'Unclassified';
      const arr = m.get(key) ?? [];
      arr.push(p);
      m.set(key, arr);
    }
    return [...m.entries()].sort(
      (a, b) =>
        b[1].reduce((s, p) => s + p.normalizedWeight, 0) -
        a[1].reduce((s, p) => s + p.normalizedWeight, 0)
    );
  }, [allRows]);

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="border-b border-border-subtle bg-bg-secondary px-4 py-4 md:px-6 md:py-5 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold">Positions</h3>
        <label className="flex items-center gap-2 text-[11px] text-text-muted select-none">
          <input
            type="checkbox"
            className="accent-[var(--accent)]"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          Former positions
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-0 text-sm md:min-w-[920px]">
          <thead>
            <tr className="text-text-muted text-xs uppercase tracking-wider">
              <th className="pl-2 pr-2 py-3 text-left md:pl-4">Ticker</th>
              <th className="px-2 py-3 text-right md:px-3">Weight</th>
              <th className="px-2 py-3 text-center md:px-3">Conviction</th>
              <th className="hidden px-3 py-3 text-right md:table-cell">Day</th>
              <th className="hidden px-3 py-3 text-right md:table-cell">Unrealized</th>
              <th className="hidden px-3 py-3 text-right lg:table-cell">Risk (stop ↔ target)</th>
              {hasTargets && (
                <>
                  <th className="hidden px-3 py-3 text-right md:table-cell">Target</th>
                  <th className="hidden px-3 py-3 text-right md:table-cell">Δ vs target</th>
                </>
              )}
              <th className="hidden max-w-[200px] px-3 py-3 text-left xl:table-cell">Thesis</th>
              <th className="px-2 py-3 text-center md:px-3">Decision</th>
              <th className="w-8 px-2 py-3 md:px-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {grouped.map(([sector, rows]) => (
              <Fragment key={sector}>
                <tr className="bg-bg-secondary/60">
                  <td
                    colSpan={colCount}
                    className="px-2 py-2 text-[11px] font-semibold uppercase tracking-wider text-text-secondary md:px-4"
                  >
                    {sector}
                    <span className="ml-2 font-mono text-text-muted">
                      {rows.reduce((s, p) => s + p.normalizedWeight, 0).toFixed(1)}%
                    </span>
                  </td>
                </tr>
                {rows.map((p) => {
                  const isExpanded = expandedTicker === p.ticker;
                  const pctOfMax = maxWeight > 0 ? (p.normalizedWeight / maxWeight) * 100 : 0;
                  const vsTarget =
                    hasTargets && p.weight_target != null
                      ? p.normalizedWeight - p.weight_target
                      : null;
                  const dec = decisionByTicker.get(p.ticker.toUpperCase());
                  return (
                    <Fragment key={p.ticker}>
                      <tr
                        onClick={() => setExpandedTicker(isExpanded ? null : p.ticker)}
                        className={`cursor-pointer transition-colors hover:bg-white/[0.03] ${
                          isExpanded ? 'bg-white/[0.02]' : ''
                        }`}
                      >
                        <td className="pl-2 pr-2 py-3 md:pl-4">
                          <span className="font-mono font-semibold text-text-primary">
                            {p.ticker}
                          </span>
                        </td>
                        <td className="px-2 py-3 text-right md:px-3">
                          <div className="flex items-center justify-end gap-2">
                            <span className="font-mono tabular-nums font-medium">
                              {p.normalizedWeight.toFixed(1)}%
                            </span>
                            <span
                              className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-bg-secondary md:inline-block"
                              aria-hidden
                            >
                              <span
                                className="block h-full rounded-full bg-[var(--accent)]/40"
                                style={{ width: `${pctOfMax}%` }}
                              />
                            </span>
                          </div>
                        </td>
                        <td className="px-2 py-3 text-center md:px-3">
                          {p.conviction != null ? (
                            <div className="flex justify-center">
                              <ConvictionMeter
                                value={Math.min(3, Math.max(1, p.conviction))}
                                max={3}
                                srLabel={`${p.ticker} conviction`}
                              />
                            </div>
                          ) : (
                            <span className="text-text-muted">—</span>
                          )}
                        </td>
                        <td
                          className={`hidden px-3 py-3 text-right font-mono tabular-nums text-xs md:table-cell ${pnlColor(
                            p.day_change_pct
                          )}`}
                        >
                          {p.day_change_pct != null
                            ? `${p.day_change_pct >= 0 ? '+' : ''}${p.day_change_pct.toFixed(1)}%`
                            : '—'}
                        </td>
                        <td
                          className={`hidden px-3 py-3 text-right font-mono tabular-nums text-xs md:table-cell ${pnlColor(
                            p.unrealized_pnl_pct
                          )}`}
                        >
                          {p.unrealized_pnl_pct != null
                            ? `${p.unrealized_pnl_pct >= 0 ? '+' : ''}${p.unrealized_pnl_pct.toFixed(1)}%`
                            : '—'}
                        </td>
                        <td className="hidden px-3 py-3 lg:table-cell">
                          <RiskEnvelopeCell
                            stopLossPct={p.stop_loss_pct}
                            targetPctGain={p.target_pct_gain}
                            horizonDays={p.horizon_days}
                          />
                        </td>
                        {hasTargets && (
                          <>
                            <td className="hidden px-3 py-3 text-right font-mono tabular-nums text-xs text-text-secondary md:table-cell">
                              {p.weight_target != null ? `${p.weight_target.toFixed(1)}%` : '—'}
                            </td>
                            <td
                              className={`hidden px-3 py-3 text-right font-mono tabular-nums text-xs md:table-cell ${
                                vsTarget != null && Math.abs(vsTarget) >= 0.05
                                  ? pnlColor(-vsTarget)
                                  : 'text-text-muted'
                              }`}
                            >
                              {vsTarget != null && Math.abs(vsTarget) >= 0.05
                                ? `${vsTarget > 0 ? '+' : ''}${vsTarget.toFixed(1)}pp`
                                : '—'}
                            </td>
                          </>
                        )}
                        <td className="hidden max-w-[200px] px-3 py-3 text-xs text-text-secondary xl:table-cell">
                          {thesisNames(p.thesis_ids, thesisById)}
                        </td>
                        <td className="px-2 py-3 text-center md:px-3">
                          {dec && dec.conviction != null ? (
                            <a
                              href={buildPipelineHref({
                                date: dec.run_date,
                                stage: 'selection',
                                node: `analyst/${p.ticker.toUpperCase()}`,
                              })}
                              onClick={(e) => e.stopPropagation()}
                              className="inline-flex items-center gap-1 text-[var(--accent)] hover:underline"
                              title={`Open ${p.ticker} decision in Pipeline`}
                            >
                              <SignedConvictionBadge value={dec.conviction} />
                              <ExternalLink size={12} aria-hidden />
                            </a>
                          ) : (
                            <span className="text-text-muted">—</span>
                          )}
                        </td>
                        <td className="px-2 py-3 text-text-muted md:px-3">
                          {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="bg-white/[0.02]">
                          <td colSpan={colCount} className="px-4 py-5 md:px-6 md:py-6">
                            <PositionDrilldown
                              key={p.ticker}
                              position={p}
                              positionHistory={positionHistory}
                              positionEvents={positionEvents}
                              thesisById={thesisById}
                              asOfDate={lastUpdated}
                              mode="allocations"
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </Fragment>
            ))}
            {reconciliation.rows.length === 0 && (
              <tr>
                <td colSpan={colCount} className="text-center py-10 text-text-muted">
                  No active positions
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {!hasTargets && (
        <p className="px-4 py-3 text-xs text-text-muted md:px-6">
          No target book yet — runs without a PM rebalance leave targets unset.
        </p>
      )}
    </div>
  );
}
