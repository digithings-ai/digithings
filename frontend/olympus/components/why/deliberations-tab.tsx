'use client';

import { useState } from 'react';
import { Calendar, FileText, GitBranch, Scale, TrendingUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import DocumentExpandInline from '@/components/library/DocumentExpandInline';
import { canonicalPmTitle } from '@/components/portfolio/tabs/palette-and-format';
import { useDashboard } from '@/lib/dashboard-context';
import { docMatchesLibraryScope } from '@/lib/library-doc-tier';
import { useLibraryDocument } from '@/lib/hooks/use-library-document';
import type { Doc, PipelineObservabilityBundle, PipelineTickerDoc } from '@/lib/types';
import {
  cleanMemoProse,
  isRebalancePayload,
  renderRebalanceMarkdown,
  isRiskDebatePayload,
  isDebateSummaryPayload,
  summarizeRecommendedPortfolio,
} from '@/lib/render-pipeline-payloads';

/**
 * Deliberations — the reasoning behind the book. The latest pipeline artifacts
 * (rebalance memo, risk debate, per-ticker bull/bear) plus the dated PM-memo
 * document history. This is the PM-process reasoning relocated out of Portfolio
 * (it is "why we hold", not "the book itself").
 */

const s = (v: unknown): string => (v == null ? '' : String(v));

/** Latest-first by ISO date (stable for equal/blank dates). */
export function sortDocsByDateDesc<T extends { date?: string | null }>(docs: T[]): T[] {
  return [...docs].sort((a, b) => (b.date || '').localeCompare(a.date || ''));
}

function PmRebalancePanel({ payload }: { payload: Record<string, unknown> }) {
  const md = renderRebalanceMarkdown(payload);
  const summary = summarizeRecommendedPortfolio(payload);
  const actions: Array<Record<string, unknown>> = Array.isArray(payload.actions)
    ? (payload.actions as Array<Record<string, unknown>>)
    : [];
  const notes = typeof payload.notes === 'string' && payload.notes.trim() ? payload.notes.trim() : '';

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-hair bg-term-bg flex items-center gap-2">
        <GitBranch size={14} className="text-accent shrink-0" aria-hidden />
        <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider">Rebalance memo</h3>
        <span className="ml-auto text-[10px] text-ink-mute font-mono">automated</span>
      </div>
      <div className="px-5 py-4 space-y-4 text-sm">
        {summary ? (
          <div className="rounded-lg border border-accent/15 bg-accent/[0.04] p-4">
            <p className="text-[11px] font-semibold text-ink-mute uppercase tracking-wider mb-3">
              Post-risk-sizing book summary
            </p>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-ink-mute">Invested</p>
                <p className="text-base font-semibold tabular-nums text-ink">
                  {summary.investedPct.toFixed(2)}%
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-ink-mute">Cash</p>
                <p className="text-base font-semibold tabular-nums text-ink">
                  {summary.cashPct.toFixed(2)}%
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-ink-mute">Holdings</p>
                <p className="text-base font-semibold tabular-nums text-ink">
                  {summary.holdingsCount}
                </p>
              </div>
            </div>
          </div>
        ) : null}
        {notes ? (
          <div>
            <p className="text-[11px] font-semibold text-ink-mute uppercase tracking-wider mb-2">
              Narrative / memo notes
            </p>
            <div className="prose prose-invert max-w-none text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanMemoProse(notes)}</ReactMarkdown>
            </div>
          </div>
        ) : null}
        {actions.length > 0 ? (
          <div className="overflow-x-auto">
            <p className="text-[11px] font-semibold text-ink-mute uppercase tracking-wider mb-2">Actions</p>
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-hair text-ink-mute">
                  <th className="py-2 pr-3 font-medium">Ticker</th>
                  <th className="py-2 pr-3 font-medium">Action</th>
                  <th className="py-2 pr-3 font-medium text-right">Current</th>
                  <th className="py-2 pr-3 font-medium text-right">Target</th>
                  <th className="py-2 font-medium">Rationale</th>
                </tr>
              </thead>
              <tbody>
                {actions.map((a, i) => {
                  const act = String(a.action ?? '').toLowerCase();
                  const acColor =
                    act === 'add' || act === 'new'
                      ? 'text-up'
                      : act === 'trim' || act === 'exit'
                        ? 'text-down/90'
                        : 'text-ink-soft';
                  const fmtPct = (v: unknown) =>
                    v == null || Number.isNaN(Number(v)) ? '—' : `${Number(v).toFixed(2)}%`;
                  const targetPct =
                    (a as Record<string, unknown>).target_pct ?? (a as Record<string, unknown>).recommended_pct;
                  return (
                    <tr key={i} className="border-b border-hair/60 align-top">
                      <td className="py-2 pr-3 font-mono text-accent">{String(a.ticker ?? '—')}</td>
                      <td className={`py-2 pr-3 font-medium ${acColor}`}>{String(a.action ?? '—')}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{fmtPct(a.current_pct)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{fmtPct(targetPct)}</td>
                      <td className="py-2 text-ink-soft whitespace-pre-wrap">
                        {cleanMemoProse(String(a.rationale ?? '—'))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : !notes ? (
          <div className="prose prose-invert max-w-none text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{md}</ReactMarkdown>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function RiskDebatePanel({ payload }: { payload: Record<string, unknown> }) {
  const agg = s(payload.aggressive_case).trim();
  const con = s(payload.conservative_case).trim();
  const tension = s(payload.key_tension).trim();

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-hair bg-term-bg flex items-center gap-2">
        <Scale size={14} className="text-warn shrink-0" aria-hidden />
        <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider">Risk debate</h3>
        <span className="ml-auto text-[10px] text-ink-mute font-mono">automated</span>
      </div>
      <div className="px-5 py-4 grid md:grid-cols-2 gap-4 text-sm">
        {agg ? (
          <div>
            <p className="text-[11px] font-semibold text-up uppercase tracking-wider mb-1">Aggressive</p>
            <p className="text-ink-soft text-xs leading-relaxed">{cleanMemoProse(agg)}</p>
          </div>
        ) : null}
        {con ? (
          <div>
            <p className="text-[11px] font-semibold text-warn uppercase tracking-wider mb-1">Conservative</p>
            <p className="text-ink-soft text-xs leading-relaxed">{cleanMemoProse(con)}</p>
          </div>
        ) : null}
        {tension ? (
          <div className="md:col-span-2 border-t border-hair pt-3">
            <p className="text-[11px] font-semibold text-ink-mute uppercase tracking-wider mb-1">Key tension</p>
            <p className="text-ink-soft text-xs leading-relaxed">{cleanMemoProse(tension)}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Per-ticker bull/bear debate summaries (`deliberation/{ticker}`). */
export function DeliberationsPanel({ docs }: { docs: PipelineTickerDoc[] }) {
  const bulletins = docs.filter((d) => isDebateSummaryPayload(d.payload));
  if (!bulletins.length) return null;

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-hair bg-term-bg flex items-center gap-2">
        <TrendingUp size={14} className="text-accent shrink-0" aria-hidden />
        <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider">Ticker debates</h3>
        <span className="ml-auto text-[10px] text-ink-mute font-mono">
          automated · {bulletins.length} ticker{bulletins.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="divide-y divide-hair">
        {bulletins.map((d) => {
          const p = d.payload;
          const stance = s(p.net_stance).trim().toLowerCase();
          const stanceColor =
            stance === 'bullish'
              ? 'text-up'
              : stance === 'bearish'
                ? 'text-down'
                : 'text-warn';
          const bull = s(p.bull_thesis).trim();
          const bear = s(p.bear_thesis).trim();
          const delta = s(p.conviction_delta).trim();
          const sign = delta && !delta.startsWith('-') && delta !== '0' ? `+${delta}` : delta;

          return (
            <div key={d.ticker} className="px-5 py-4 space-y-3">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-sm font-semibold text-accent">{d.ticker}</span>
                {stance ? <span className={`text-xs font-medium capitalize ${stanceColor}`}>{stance}</span> : null}
                {delta ? <span className="text-[11px] text-ink-mute">conviction Δ {sign}</span> : null}
              </div>
              <div className="grid md:grid-cols-2 gap-3 text-xs text-ink-soft leading-relaxed">
                {bull ? (
                  <div>
                    <p className="text-[10px] font-semibold text-up/80 uppercase tracking-wider mb-1">Bull</p>
                    <p>{cleanMemoProse(bull)}</p>
                  </div>
                ) : null}
                {bear ? (
                  <div>
                    <p className="text-[10px] font-semibold text-down/80 uppercase tracking-wider mb-1">Bear</p>
                    <p>{cleanMemoProse(bear)}</p>
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function hasPipelineArtifacts(pipe: PipelineObservabilityBundle | null): boolean {
  if (!pipe) return false;
  return (
    isRebalancePayload(pipe.pm_rebalance) ||
    isRiskDebatePayload(pipe.risk_debate) ||
    pipe.deliberation_transcripts.some((d) => isDebateSummaryPayload(d.payload))
  );
}

export function DeliberationsTab() {
  const { data } = useDashboard();
  const pipe = data?.pipeline_observability ?? null;
  const pmDocs = sortDocsByDateDesc((data?.docs ?? []).filter((d) => docMatchesLibraryScope(d, 'portfolio')));

  const [activeId, setActiveId] = useState<string | null>(null);
  const activeFile: Doc | null = pmDocs.find((d) => d.id === activeId) ?? null;
  const { loading: docLoading, data: libraryDoc } = useLibraryDocument(activeFile);

  const showArtifacts = hasPipelineArtifacts(pipe);

  if (!showArtifacts && pmDocs.length === 0) {
    return (
      <div className="glass-card px-5 py-12 text-center text-sm text-ink-mute">
        No deliberations yet — bull/bear debates, the risk debate, and the rebalance memo appear here after a run.
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {showArtifacts && pipe ? (
        <section className="space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-[11px] font-semibold text-ink-mute tracking-wide">Latest run</p>
            {pipe.snapshot_date ? (
              <span className="text-[11px] text-ink-mute font-mono">{pipe.snapshot_date}</span>
            ) : null}
          </div>
          {isRebalancePayload(pipe.pm_rebalance) && pipe.pm_rebalance ? (
            <PmRebalancePanel payload={pipe.pm_rebalance} />
          ) : null}
          {isRiskDebatePayload(pipe.risk_debate) && pipe.risk_debate ? (
            <RiskDebatePanel payload={pipe.risk_debate} />
          ) : null}
          {pipe.deliberation_transcripts.length > 0 ? (
            <DeliberationsPanel docs={pipe.deliberation_transcripts} />
          ) : null}
        </section>
      ) : null}

      {pmDocs.length > 0 ? (
        <section className="space-y-3">
          <div className="flex items-center gap-2 px-0.5">
            <Calendar size={15} className="text-warn shrink-0" aria-hidden />
            <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider">PM memo history</h3>
            <span className="text-[11px] text-ink-mute">{pmDocs.length} document{pmDocs.length !== 1 ? 's' : ''}</span>
          </div>
          <div className="glass-card p-0 overflow-hidden">
            <div className="divide-y divide-hair">
              {pmDocs.map((d) => {
                const active = activeId === d.id;
                return (
                  <div key={d.id}>
                    <button
                      type="button"
                      onClick={() => setActiveId(active ? null : d.id)}
                      aria-expanded={active}
                      className={`w-full text-left px-5 py-3 flex items-center gap-3 hover:bg-ink/[0.03] transition-colors ${
                        active ? 'bg-warn/[0.06]' : ''
                      }`}
                    >
                      <FileText size={14} className="text-warn/70 shrink-0" />
                      <span className="font-mono text-sm">{canonicalPmTitle(d.path)}</span>
                      <span className="ml-auto text-[11px] font-mono text-ink-mute">{d.date ?? ''}</span>
                    </button>
                    {active ? (
                      <DocumentExpandInline
                        accent="amber"
                        hideTitleBar
                        title={canonicalPmTitle(d.path)}
                        subtitle={d.date ?? null}
                        loading={docLoading}
                        libraryDoc={libraryDoc}
                      />
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
