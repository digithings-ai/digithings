'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useDashboard } from '@/lib/dashboard-context';
import { Badge } from '@/components/ui';
import { renderDocumentMarkdownFromPayload } from '@/lib/render-document-from-payload';
import { getThesisHistoryById } from '@/lib/queries';
import { aggregateWeightByThesis } from '@/lib/portfolio-aggregates';
import {
  AlertTriangle,
  ArrowUpRight,
  ArrowRightLeft,
  Target,
  TrendingUp,
} from 'lucide-react';
import type { Thesis, ProposedPosition, RebalanceAction, ThesisHistoryPoint } from '@/lib/types';

interface RegimeColorSet {
  text: string;
  border: string;
}

const regimeColors: Record<string, RegimeColorSet> = {
  bullish: { text: 'text-fin-green', border: 'border-fin-green/40' },
  bearish: { text: 'text-fin-red', border: 'border-fin-red/40' },
  caution: { text: 'text-fin-amber', border: 'border-fin-amber/40' },
  neutral: { text: 'text-fin-blue', border: 'border-fin-blue/40' },
};

function statusColor(status: string | null | undefined): string {
  const s = (status || '').toLowerCase();
  if (s.includes('confirmed') || s.includes('active')) return 'text-fin-green';
  if (s.includes('monitoring') || s.includes('watch')) return 'text-fin-amber';
  if (s.includes('invalidated') || s.includes('broken') || s.includes('challenged')) return 'text-fin-red';
  return 'text-text-muted';
}

function actionColor(action: string | null | undefined): string {
  const a = (action || '').toLowerCase();
  if (a.includes('exit')) return 'text-fin-red';
  if (a.includes('new')) return 'text-fin-green';
  if (a.includes('add')) return 'text-fin-blue';
  if (a.includes('trim')) return 'text-fin-amber';
  if (a === 'hold') return 'text-text-muted';
  return 'text-fin-amber';
}

function escapeAttrSelector(id: string): string {
  try {
    const esc = globalThis.CSS?.escape;
    return typeof esc === 'function' ? esc(id) : id.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  } catch {
    return id.replace(/[^a-zA-Z0-9_-]/g, '_');
  }
}

export type StrategyThesisPanelProps = {
  /** `thesis` URL value for row highlight and DB history */
  highlightThesisId: string | null;
  thesisHref: (thesisId: string) => string;
  clearThesisHref: string;
};

/**
 * Regime, pipeline markdown, digest theses, PM proposals, actionable/risks.
 * Used on Portfolio Analysis and (via redirect) legacy /strategy links.
 */
export default function StrategyThesisPanel({
  highlightThesisId,
  thesisHref,
  clearThesisHref,
}: StrategyThesisPanelProps) {
  const { data } = useDashboard();
  const [thesisHistory, setThesisHistory] = useState<ThesisHistoryPoint[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const exposureByThesis = useMemo(
    () => aggregateWeightByThesis(data?.positions ?? []),
    [data?.positions]
  );

  useEffect(() => {
    if (!highlightThesisId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset when selection cleared
      setThesisHistory([]);
      return;
    }
    setHistoryLoading(true);
    let cancelled = false;
    getThesisHistoryById(highlightThesisId)
      .then((rows) => {
        if (!cancelled) setThesisHistory(rows);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [highlightThesisId]);

  useEffect(() => {
    if (!highlightThesisId || !data) return;
    const id = requestAnimationFrame(() => {
      const sel = `[data-thesis-id="${escapeAttrSelector(highlightThesisId)}"]`;
      document.querySelector(sel)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    return () => cancelAnimationFrame(id);
  }, [highlightThesisId, data]);

  if (!data) return null;

  const { strategy } = data.portfolio;
  const pm = data.portfolio_management || {};
  const theses: Thesis[] = strategy.theses || [];
  const proposed: ProposedPosition[] = pm.proposed_positions || [];
  const rebalance: RebalanceAction[] = pm.rebalance_actions || [];
  const contextBullets = data.snapshot_context_bullets ?? [];

  const regimeLabel = strategy.regime_label || 'neutral';
  const rc = regimeColors[regimeLabel] || regimeColors.neutral;

  const pipe = data.pipeline_observability;
  const marketThesisMarkdown = pipe?.market_thesis_exploration
    ? renderDocumentMarkdownFromPayload(pipe.market_thesis_exploration)
    : null;
  const vehicleMapMarkdown = pipe?.thesis_vehicle_map
    ? renderDocumentMarkdownFromPayload(pipe.thesis_vehicle_map)
    : null;

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border-subtle/80 bg-gradient-to-br from-bg-secondary/40 to-transparent px-4 py-3 sm:px-5">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-text-muted mb-3">
          Strategy snapshot
        </p>
        <div className={`glass-card p-5 sm:p-6 border-l-4 ${rc.border}`}>
          <div className="flex flex-col sm:flex-row justify-between gap-4">
            <div>
              <p className={`text-xs font-semibold uppercase tracking-widest mb-1 ${rc.text}`}>
                Current macro regime
              </p>
              <h2 className="text-lg sm:text-xl font-bold">{strategy.regime}</h2>
              <p className="text-text-secondary mt-2 leading-relaxed max-w-2xl text-sm">
                {strategy.summary}
              </p>
              {contextBullets.length > 0 ? (
                <ul className="mt-4 space-y-1 text-xs text-text-muted border-t border-border-subtle/80 pt-3">
                  {contextBullets.map((b, i) => (
                    <li key={i} className="pl-3 border-l-2 border-fin-blue/30">
                      {b}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            <Badge variant="default" className="h-fit shrink-0">
              Next review: {strategy.next_review}
            </Badge>
          </div>
        </div>
      </div>

      {(marketThesisMarkdown || vehicleMapMarkdown) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {marketThesisMarkdown ? (
            <details open className="group glass-card p-0 overflow-hidden">
              <summary className="cursor-pointer list-none px-5 py-4 border-b border-border-subtle bg-bg-secondary flex items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold">Market thesis exploration</h3>
                  <p className="text-xs text-text-muted mt-0.5">
                    Track B ·{' '}
                    <span className="font-mono text-text-secondary">{pipe?.snapshot_date}</span>
                  </p>
                </div>
                <span className="text-xs text-text-muted group-open:hidden">Show</span>
                <span className="text-xs text-text-muted hidden group-open:inline">Hide</span>
              </summary>
              <div className="px-5 py-4 prose prose-invert max-w-none text-sm leading-relaxed max-h-[min(70vh,520px)] overflow-y-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{marketThesisMarkdown}</ReactMarkdown>
              </div>
            </details>
          ) : null}
          {vehicleMapMarkdown ? (
            <details open className="group glass-card p-0 overflow-hidden">
              <summary className="cursor-pointer list-none px-5 py-4 border-b border-border-subtle bg-bg-secondary flex items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold">Thesis → vehicle map</h3>
                  <p className="text-xs text-text-muted mt-0.5">
                    <span className="font-mono text-text-secondary">{pipe?.snapshot_date}</span>
                  </p>
                </div>
                <span className="text-xs text-text-muted group-open:hidden">Show</span>
                <span className="text-xs text-text-muted hidden group-open:inline">Hide</span>
              </summary>
              <div className="px-5 py-4 prose prose-invert max-w-none text-sm leading-relaxed max-h-[min(70vh,520px)] overflow-y-auto">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{vehicleMapMarkdown}</ReactMarkdown>
              </div>
            </details>
          ) : null}
        </div>
      )}

      {theses.length > 0 && (
        <div className="glass-card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-border-subtle bg-bg-secondary flex items-center gap-2">
            <Target size={16} className="text-fin-blue shrink-0" />
            <div>
              <h3 className="text-sm font-semibold">Active theses (digest)</h3>
              <p className="text-xs text-text-muted">Live book exposure · click ID for history</p>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-0 text-sm md:min-w-[820px]">
              <thead>
                <tr className="border-b border-border-subtle text-xs uppercase tracking-wider text-text-muted">
                  <th className="px-4 py-3 text-left md:px-5">ID</th>
                  <th className="px-4 py-3 text-left md:px-5">Thesis</th>
                  <th className="px-4 py-3 text-right md:px-5">Exposure</th>
                  <th className="hidden px-5 py-3 text-left md:table-cell">Vehicle</th>
                  <th className="hidden px-5 py-3 text-left lg:table-cell">Invalidation</th>
                  <th className="px-4 py-3 text-left md:px-5">Status</th>
                  <th className="hidden px-5 py-3 text-left xl:table-cell">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {theses.map((t, i) => (
                  <tr
                    key={i}
                    data-thesis-id={t.id}
                    className={`hover:bg-white/[0.02] ${
                      highlightThesisId === t.id ? 'bg-fin-blue/10 ring-1 ring-fin-blue/30' : ''
                    }`}
                  >
                    <td className="px-4 py-3 font-mono md:px-5">
                      <Link href={thesisHref(t.id)} className="text-fin-blue hover:underline">
                        {t.id}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-medium md:px-5">{t.name}</td>
                    <td className="px-4 py-3 text-right font-mono font-semibold tabular-nums md:px-5">
                      {(exposureByThesis.get(t.id) ?? 0).toFixed(1)}%
                    </td>
                    <td className="hidden px-5 py-3 font-mono text-[0.85rem] text-text-secondary md:table-cell">
                      {t.vehicle}
                    </td>
                    <td className="hidden px-5 py-3 text-[0.85rem] text-text-muted lg:table-cell">{t.invalidation}</td>
                    <td className={`px-4 py-3 font-semibold md:px-5 ${statusColor(t.status)}`}>{t.status}</td>
                    <td className="hidden px-5 py-3 text-[0.85rem] text-text-secondary xl:table-cell">{t.notes}</td>
                  </tr>
                ))}
                {(exposureByThesis.get('_unlinked') ?? 0) > 0.005 && (
                  <tr className="bg-white/[0.02] hover:bg-white/[0.02]">
                    <td className="px-4 py-3 font-mono text-text-muted md:px-5">—</td>
                    <td className="px-4 py-3 font-medium text-text-secondary md:px-5">Unlinked positions</td>
                    <td className="px-4 py-3 text-right font-mono font-semibold tabular-nums md:px-5">
                      {(exposureByThesis.get('_unlinked') ?? 0).toFixed(1)}%
                    </td>
                    <td colSpan={4} className="px-4 py-3 text-xs text-text-muted md:px-5">
                      No thesis_id on digest positions
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {highlightThesisId ? (
            <div className="border-t border-border-subtle px-5 py-4 bg-bg-secondary/40">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <h4 className="text-sm font-semibold text-text-primary">
                  Thesis history <span className="font-mono text-fin-blue">{highlightThesisId}</span>
                </h4>
                <Link href={clearThesisHref} className="text-xs text-text-muted hover:text-white">
                  Clear selection
                </Link>
              </div>
              {historyLoading ? (
                <p className="text-xs text-text-muted">Loading history…</p>
              ) : thesisHistory.length === 0 ? (
                <p className="text-xs text-text-muted">No historical rows in the theses table for this id.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-0 text-xs md:min-w-[640px]">
                    <thead>
                      <tr className="text-text-muted uppercase tracking-wider border-b border-border-subtle">
                        <th className="text-left py-2 pr-4">Date</th>
                        <th className="text-left py-2 pr-4">Name</th>
                        <th className="text-left py-2 pr-4">Status</th>
                        <th className="text-left py-2">Notes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-subtle/80">
                      {thesisHistory.map((row) => (
                        <tr key={`${row.date}-${row.thesis_id}`}>
                          <td className="py-2 pr-4 font-mono text-text-secondary whitespace-nowrap">
                            {row.date}
                          </td>
                          <td className="py-2 pr-4">{row.name}</td>
                          <td className={`py-2 pr-4 ${statusColor(row.status)}`}>{row.status ?? '—'}</td>
                          <td className="py-2 text-text-muted max-w-md truncate">{row.notes ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}

      {(proposed.length > 0 || rebalance.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {proposed.length > 0 && (
            <div className="glass-card p-0 overflow-hidden">
              <div className="px-5 py-4 border-b border-border-subtle bg-bg-secondary flex items-center gap-2">
                <TrendingUp size={16} className="text-fin-amber shrink-0" />
                <h3 className="text-sm font-semibold">Proposed positions</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-text-muted text-xs uppercase tracking-wider border-b border-border-subtle">
                      <th className="text-left px-5 py-3">Ticker</th>
                      <th className="text-right px-5 py-3">Weight</th>
                      <th className="text-left px-5 py-3">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {proposed.map((p, i) => (
                      <tr key={i} className="hover:bg-white/[0.02]">
                        <td className="px-5 py-3 font-semibold">{p.ticker}</td>
                        <td className="px-5 py-3 text-right">{p.weight_pct}%</td>
                        <td className={`px-5 py-3 ${actionColor(p.action)}`}>{p.action}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {rebalance.length > 0 && (
            <div className="glass-card p-0 overflow-hidden">
              <div className="px-5 py-4 border-b border-border-subtle bg-bg-secondary flex items-center gap-2">
                <ArrowRightLeft size={16} className="text-fin-blue shrink-0" />
                <h3 className="text-sm font-semibold">Rebalance actions</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-text-muted text-xs uppercase tracking-wider border-b border-border-subtle">
                      <th className="text-left px-5 py-3">Ticker</th>
                      <th className="text-right px-5 py-3">Current</th>
                      <th className="text-right px-5 py-3">Target</th>
                      <th className="text-left px-5 py-3">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {rebalance.map((r, i) => (
                      <tr key={i} className="hover:bg-white/[0.02]">
                        <td className="px-5 py-3 font-semibold">{r.ticker}</td>
                        <td className="px-5 py-3 text-right">{r.current_pct}%</td>
                        <td className="px-5 py-3 text-right">{r.recommended_pct}%</td>
                        <td className={`px-5 py-3 ${actionColor(r.action)}`}>{r.action}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="glass-card p-5">
          <div className="flex items-center gap-2 mb-3">
            <ArrowUpRight size={16} className="text-fin-green shrink-0" />
            <h3 className="text-sm font-semibold">Actionable summary</h3>
          </div>
          <ul className="space-y-2 text-sm text-text-secondary leading-relaxed pl-4 list-disc">
            {strategy.actionable?.length > 0 ? (
              strategy.actionable.map((a, i) => <li key={i}>{a}</li>)
            ) : (
              <li className="text-text-muted">No actionable items extracted.</li>
            )}
          </ul>
        </div>
        <div className="glass-card p-5 bg-gradient-to-b from-fin-red/5 to-transparent">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={16} className="text-fin-red shrink-0" />
            <h3 className="text-sm font-semibold">Risk radar</h3>
          </div>
          <ul className="space-y-2 text-sm text-red-300 leading-relaxed pl-4 list-disc">
            {strategy.risks?.length > 0 ? (
              strategy.risks.map((r, i) => <li key={i}>{r}</li>)
            ) : (
              <li className="text-text-muted">No immediate risks flagged.</li>
            )}
          </ul>
        </div>
      </div>

      <div className="relative py-2">
        <div className="absolute inset-0 flex items-center" aria-hidden>
          <div className="w-full border-t border-border-subtle" />
        </div>
        <div className="relative flex justify-center">
          <span className="rounded-full border border-border-subtle bg-bg-secondary px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-text-muted">
            Book over time &amp; PM process
          </span>
        </div>
      </div>
    </div>
  );
}
