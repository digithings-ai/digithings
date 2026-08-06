'use client';

import { useState } from 'react';
import { Calendar, FileText, GitBranch, Scale, TrendingUp } from 'lucide-react';
import DocumentExpandInline from '@/components/library/DocumentExpandInline';
import { SafeMarkdown } from '@/components/SafeMarkdown';
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

/**
 * Run-level PM record for the memo history list. With the Documents tab
 * retired, this list is the last archive surface for run-level portfolio
 * docs (allocation memos, thesis exploration, vehicle maps, screeners,
 * legacy deliberations) — only per-ticker artifacts are excluded, since
 * those already surface in the Latest-run panels and Pipeline node detail.
 */
export function isPmMemoHistoryDoc(doc: Pick<Doc, 'path'>): boolean {
  const path = (doc.path || '').toLowerCase();
  return !(
    path.startsWith('deliberation/') ||
    path.startsWith('deliberation-transcript/') ||
    path.startsWith('deliberation-transcript-index/') ||
    path.startsWith('asset-recommendations/')
  );
}

export function PmRebalancePanel({ payload }: { payload: Record<string, unknown> }) {
  const md = renderRebalanceMarkdown(payload);
  const summary = summarizeRecommendedPortfolio(payload);
  const actions: Array<Record<string, unknown>> = Array.isArray(payload.actions)
    ? (payload.actions as Array<Record<string, unknown>>)
    : [];
  const notes = typeof payload.notes === 'string' && payload.notes.trim() ? payload.notes.trim() : '';

  return (
    <section data-testid="rebalance-ledger" className="border-y border-hair">
      <div className="px-5 py-3 border-b border-hair bg-term-bg flex items-center gap-2">
        <GitBranch size={14} className="text-accent shrink-0" aria-hidden />
        <h3 className="text-xs font-semibold uppercase text-ink-mute">Rebalance memo</h3>
        <span className="ml-auto font-mono text-xs text-ink-mute">automated</span>
      </div>
      <div className="px-5 py-4 space-y-4 text-sm">
        {summary ? (
          <div>
            <p className="mb-3 text-xs font-semibold uppercase text-ink-mute">
              Post-risk-sizing book summary
            </p>
            <dl className="grid grid-cols-3 gap-px border-y border-hair bg-hair text-xs">
              <div className="bg-surface px-3 py-3">
                <dt className="uppercase text-ink-mute">Invested</dt>
                <dd className="text-base font-semibold tabular-nums text-ink">
                  {summary.investedPct.toFixed(2)}%
                </dd>
              </div>
              <div className="bg-surface px-3 py-3">
                <dt className="uppercase text-ink-mute">Cash</dt>
                <dd className="text-base font-semibold tabular-nums text-ink">
                  {summary.cashPct.toFixed(2)}%
                </dd>
              </div>
              <div className="bg-surface px-3 py-3">
                <dt className="uppercase text-ink-mute">Holdings</dt>
                <dd className="text-base font-semibold tabular-nums text-ink">
                  {summary.holdingsCount}
                </dd>
              </div>
            </dl>
          </div>
        ) : null}
        {notes ? (
          <div>
            <p className="mb-2 text-xs font-semibold uppercase text-ink-mute">
              Narrative / memo notes
            </p>
            <SafeMarkdown>{cleanMemoProse(notes)}</SafeMarkdown>
          </div>
        ) : null}
        {actions.length > 0 ? (
          <div className="overflow-x-auto">
            <p className="mb-2 text-xs font-semibold uppercase text-ink-mute">Actions</p>
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
                      ? 'text-accent'
                      : act === 'trim' || act === 'exit'
                        ? 'text-warn'
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
          <SafeMarkdown>{md}</SafeMarkdown>
        ) : null}
      </div>
    </section>
  );
}

export function RiskDebatePanel({ payload }: { payload: Record<string, unknown> }) {
  const agg = s(payload.aggressive_case).trim();
  const con = s(payload.conservative_case).trim();
  const tension = s(payload.key_tension).trim();

  return (
    <section data-testid="risk-debate-ledger" className="border-y border-hair">
      <div className="px-5 py-3 border-b border-hair bg-term-bg flex items-center gap-2">
        <Scale size={14} className="text-warn shrink-0" aria-hidden />
        <h3 className="text-xs font-semibold uppercase text-ink-mute">Risk debate</h3>
        <span className="ml-auto font-mono text-xs text-ink-mute">automated</span>
      </div>
      <div className="px-5 py-4 grid md:grid-cols-2 gap-4 text-sm">
        {agg ? (
          <div>
            <p className="mb-1 text-xs font-semibold uppercase text-accent">Aggressive</p>
            <p className="text-ink-soft text-xs leading-relaxed">{cleanMemoProse(agg)}</p>
          </div>
        ) : null}
        {con ? (
          <div>
            <p className="mb-1 text-xs font-semibold uppercase text-warn">Conservative</p>
            <p className="text-ink-soft text-xs leading-relaxed">{cleanMemoProse(con)}</p>
          </div>
        ) : null}
        {tension ? (
          <div className="md:col-span-2 border-t border-hair pt-3">
            <p className="mb-1 text-xs font-semibold uppercase text-ink-mute">Key tension</p>
            <p className="text-ink-soft text-xs leading-relaxed">{cleanMemoProse(tension)}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}

/** Per-ticker bull/bear debate summaries (`deliberation/{ticker}`). */
export function DeliberationsPanel({ docs }: { docs: PipelineTickerDoc[] }) {
  const bulletins = docs.filter((d) => isDebateSummaryPayload(d.payload));
  if (!bulletins.length) return null;

  return (
    <section data-testid="ticker-debate-ledger" className="border-y border-hair">
      <div className="px-5 py-3 border-b border-hair bg-term-bg flex items-center gap-2">
        <TrendingUp size={14} className="text-accent shrink-0" aria-hidden />
        <h3 className="text-xs font-semibold uppercase text-ink-mute">Ticker debates</h3>
        <span className="ml-auto font-mono text-xs text-ink-mute">
          automated · {bulletins.length} ticker{bulletins.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="divide-y divide-hair">
        {bulletins.map((d) => {
          const p = d.payload;
          const stance = s(p.net_stance).trim().toLowerCase();
          const stanceColor =
            stance === 'bullish'
              ? 'text-accent'
              : stance === 'bearish'
                ? 'text-warn'
                : 'text-ink-mute';
          const bull = s(p.bull_thesis).trim();
          const bear = s(p.bear_thesis).trim();
          const delta = s(p.conviction_delta).trim();
          const sign = delta && !delta.startsWith('-') && delta !== '0' ? `+${delta}` : delta;

          return (
            <div key={d.ticker} className="px-5 py-4 space-y-3">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-sm font-semibold text-accent">{d.ticker}</span>
                {stance ? <span className={`text-xs font-medium capitalize ${stanceColor}`}>{stance}</span> : null}
                {delta ? <span className="text-xs text-ink-mute">conviction Δ {sign}</span> : null}
              </div>
              <div className="grid md:grid-cols-2 gap-3 text-xs text-ink-soft leading-relaxed">
                {bull ? (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase text-accent">Bull</p>
                    <p>{cleanMemoProse(bull)}</p>
                  </div>
                ) : null}
                {bear ? (
                  <div>
                    <p className="mb-1 text-xs font-semibold uppercase text-warn">Bear</p>
                    <p>{cleanMemoProse(bear)}</p>
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>
    </section>
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
  const pmDocs = sortDocsByDateDesc(
    (data?.docs ?? [])
      .filter((d) => docMatchesLibraryScope(d, 'portfolio'))
      .filter(isPmMemoHistoryDoc),
  );

  const [activeId, setActiveId] = useState<string | null>(null);
  const activeFile: Doc | null = pmDocs.find((d) => d.id === activeId) ?? null;
  const { loading: docLoading, data: libraryDoc } = useLibraryDocument(activeFile);

  const showArtifacts = hasPipelineArtifacts(pipe);

  if (!showArtifacts && pmDocs.length === 0) {
    return (
      <div className="border-y border-hair px-5 py-12 text-center text-sm text-ink-mute">
        No deliberations yet — bull/bear debates, the risk debate, and the rebalance memo appear here after a run.
      </div>
    );
  }

  return (
    <div data-testid="why-deliberations-workspace" className="space-y-8">
      {showArtifacts && pipe ? (
        <section className="space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-xs font-semibold text-ink-mute">Latest run</p>
            {pipe.snapshot_date ? (
              <span className="font-mono text-xs text-ink-mute">{pipe.snapshot_date}</span>
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
            <h3 className="text-xs font-semibold uppercase text-ink-mute">PM memo history</h3>
            <span className="text-xs text-ink-mute">{pmDocs.length} document{pmDocs.length !== 1 ? 's' : ''}</span>
          </div>
          <div className="border-y border-hair">
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
                      <span className="ml-auto font-mono text-xs text-ink-mute">{d.date ?? ''}</span>
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
