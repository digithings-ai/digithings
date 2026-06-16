'use client';

import { useCallback } from 'react';
import { Calendar, FileText, GitBranch, Scale, TrendingUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import MiniCalendar, { type MiniCalendarRunKind } from '@/components/library/MiniCalendar';
import DocumentExpandInline from '@/components/library/DocumentExpandInline';
import type { Doc, PipelineObservabilityBundle, PipelineTickerDoc } from '@/lib/types';
import type { LibraryDocumentResult } from '@/lib/queries';
import { groupPmDocs, canonicalPmTitle } from '@/components/portfolio/tabs/palette-and-format';
import { useDashboard } from '@/lib/dashboard-context';
import {
  isRebalancePayload,
  renderRebalanceMarkdown,
  isRiskDebatePayload,
  isDebateSummaryPayload,
} from '@/lib/render-pipeline-payloads';

// ─────────────────────────────────────────────────────────────────────────────
// Inline pipeline artifact panels (automated prod path — Hermes pipeline)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Renders the PM rebalance decision artifact if it has the live automated shape.
 * We use the raw payload so we can render it inline without a library round-trip.
 */
function PmRebalancePanel({ payload }: { payload: Record<string, unknown> }) {
  const md = renderRebalanceMarkdown(payload);
  const actions: Array<Record<string, unknown>> = Array.isArray(payload.actions)
    ? (payload.actions as Array<Record<string, unknown>>)
    : [];
  const notes =
    typeof payload.notes === 'string' && payload.notes.trim() ? payload.notes.trim() : '';

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-border-subtle bg-bg-secondary flex items-center gap-2">
        <GitBranch size={14} className="text-fin-blue shrink-0" aria-hidden />
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          Rebalance Memo
        </h3>
        <span className="ml-auto text-[10px] text-text-muted font-mono">automated</span>
      </div>
      <div className="px-5 py-4 space-y-4 text-sm">
        {notes ? (
          <div className="prose prose-invert max-w-none text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{notes}</ReactMarkdown>
          </div>
        ) : null}
        {actions.length > 0 ? (
          <div className="overflow-x-auto">
            <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-2">
              Actions
            </p>
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border-subtle text-text-muted">
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
                      ? 'text-fin-green'
                      : act === 'trim' || act === 'exit'
                        ? 'text-fin-red/90'
                        : 'text-text-secondary';
                  const fmtPct = (v: unknown) =>
                    v == null || Number.isNaN(Number(v)) ? '—' : `${Number(v).toFixed(2)}%`;
                  // Live shape: `target_pct`; fixture / test payloads: `recommended_pct`.
                  const targetPct =
                    (a as Record<string, unknown>).target_pct ??
                    (a as Record<string, unknown>).recommended_pct;
                  return (
                    <tr key={i} className="border-b border-border-subtle/60 align-top">
                      <td className="py-2 pr-3 font-mono text-fin-blue">{String(a.ticker ?? '—')}</td>
                      <td className={`py-2 pr-3 font-medium ${acColor}`}>{String(a.action ?? '—')}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{fmtPct(a.current_pct)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{fmtPct(targetPct)}</td>
                      <td className="py-2 text-text-secondary whitespace-pre-wrap">
                        {String(a.rationale ?? '—')}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : !notes ? (
          // Fall back to raw markdown rendering if the structured view has nothing
          <div className="prose prose-invert max-w-none text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{md}</ReactMarkdown>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Renders the aggressive-vs-conservative risk debate (Hermes `risk-debate` doc). */
function RiskDebatePanel({ payload }: { payload: Record<string, unknown> }) {
  const s = (v: unknown) => (v == null ? '' : String(v));
  const agg = s(payload.aggressive_case).trim();
  const con = s(payload.conservative_case).trim();
  const tension = s(payload.key_tension).trim();

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-border-subtle bg-bg-secondary flex items-center gap-2">
        <Scale size={14} className="text-fin-amber shrink-0" aria-hidden />
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          Risk Debate
        </h3>
        <span className="ml-auto text-[10px] text-text-muted font-mono">automated</span>
      </div>
      <div className="px-5 py-4 grid md:grid-cols-2 gap-4 text-sm">
        {agg ? (
          <div>
            <p className="text-[11px] font-semibold text-fin-green uppercase tracking-wider mb-1">
              Aggressive
            </p>
            <p className="text-text-secondary text-xs leading-relaxed">{agg}</p>
          </div>
        ) : null}
        {con ? (
          <div>
            <p className="text-[11px] font-semibold text-fin-amber uppercase tracking-wider mb-1">
              Conservative
            </p>
            <p className="text-text-secondary text-xs leading-relaxed">{con}</p>
          </div>
        ) : null}
        {tension ? (
          <div className="md:col-span-2 border-t border-border-subtle pt-3">
            <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-1">
              Key tension
            </p>
            <p className="text-text-secondary text-xs leading-relaxed">{tension}</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Renders all per-ticker bull/bear debate summaries (Hermes `deliberation/{ticker}` docs).
 * Only the DebateSummary-shaped entries are shown (those with `net_stance`).
 */
function DeliberationsPanel({ docs }: { docs: PipelineTickerDoc[] }) {
  // Filter to the automated Hermes DebateSummary shape — drop any legacy operator docs
  const bulletins = docs.filter((d) => isDebateSummaryPayload(d.payload));
  if (!bulletins.length) return null;

  const s = (v: unknown) => (v == null ? '' : String(v));

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-border-subtle bg-bg-secondary flex items-center gap-2">
        <TrendingUp size={14} className="text-fin-purple shrink-0" aria-hidden />
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          Deliberations
        </h3>
        <span className="ml-auto text-[10px] text-text-muted font-mono">automated · {bulletins.length} ticker{bulletins.length !== 1 ? 's' : ''}</span>
      </div>
      <div className="divide-y divide-border-subtle">
        {bulletins.map((d) => {
          const p = d.payload;
          const stance = s(p.net_stance).trim().toLowerCase();
          const stanceColor =
            stance === 'bullish'
              ? 'text-fin-green'
              : stance === 'bearish'
                ? 'text-fin-red'
                : 'text-fin-amber';
          const bull = s(p.bull_thesis).trim();
          const bear = s(p.bear_thesis).trim();
          const delta = s(p.conviction_delta).trim();
          const sign = delta && !delta.startsWith('-') && delta !== '0' ? `+${delta}` : delta;

          return (
            <div key={d.ticker} className="px-5 py-4 space-y-3">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-sm font-semibold text-fin-blue">{d.ticker}</span>
                {stance ? (
                  <span className={`text-xs font-medium capitalize ${stanceColor}`}>{stance}</span>
                ) : null}
                {delta ? (
                  <span className="text-[11px] text-text-muted">conviction Δ {sign}</span>
                ) : null}
              </div>
              <div className="grid md:grid-cols-2 gap-3 text-xs text-text-secondary leading-relaxed">
                {bull ? (
                  <div>
                    <p className="text-[10px] font-semibold text-fin-green/80 uppercase tracking-wider mb-1">
                      Bull
                    </p>
                    <p>{bull}</p>
                  </div>
                ) : null}
                {bear ? (
                  <div>
                    <p className="text-[10px] font-semibold text-fin-red/80 uppercase tracking-wider mb-1">
                      Bear
                    </p>
                    <p>{bear}</p>
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

/** True when the pipeline_observability bundle has at least one renderable automated artifact. */
function hasPipelineArtifacts(pipe: PipelineObservabilityBundle | null): boolean {
  if (!pipe) return false;
  return (
    isRebalancePayload(pipe.pm_rebalance) ||
    isRiskDebatePayload(pipe.risk_debate) ||
    pipe.deliberation_transcripts.some((d) => isDebateSummaryPayload(d.payload))
  );
}

// ─────────────────────────────────────────────────────────────────────────────

export default function AnalysisTab(props: {
  historyTimelineDates: string[];
  portfolioHistoryRunKindByDate: Map<string, MiniCalendarRunKind>;
  effHistoryDate: string | null;
  onSelectHistoryDate: (iso: string) => void;
  historyLatestDate: string | null;
  onClearHistoryDate: () => void;
  portfolioDocDates: Set<string>;
  positionHistoryDates: Set<string>;
  pmDocsForHistory: Doc[];
  pmActiveFile: Doc | null;
  pmLibraryDoc: LibraryDocumentResult | null;
  pmLoading: boolean;
  onOpenPmDocument: (doc: Doc) => void;
  onClosePmDocument: () => void;
}) {
  const {
    historyTimelineDates,
    portfolioHistoryRunKindByDate,
    effHistoryDate,
    onSelectHistoryDate,
    historyLatestDate,
    onClearHistoryDate,
    portfolioDocDates,
    positionHistoryDates,
    pmDocsForHistory,
    pmActiveFile,
    pmLibraryDoc,
    pmLoading,
    onOpenPmDocument,
    onClosePmDocument,
  } = props;

  // Pull pipeline_observability from the dashboard context so we can render
  // the automated Hermes pipeline artifacts (pm_rebalance, risk_debate,
  // deliberation_transcripts) directly — these are never written as library
  // docs in the automated prod path, so the Track-B doc section below is
  // always empty in automated prod. We render them first; the Track-B section
  // remains as a graceful fallback for analyst-authored sessions.
  const { data } = useDashboard();
  const pipe = data?.pipeline_observability ?? null;
  const showPipelineArtifacts = hasPipelineArtifacts(pipe);

  const selectHistoryDate = useCallback(
    (iso: string) => {
      onSelectHistoryDate(iso);
    },
    [onSelectHistoryDate]
  );

  return (
    <div className="flex gap-6 max-lg:flex-col">
      <div className="w-56 shrink-0 space-y-4 max-lg:w-full max-lg:flex max-lg:gap-4 max-lg:flex-wrap">
        <div className="space-y-2">
          <p className="text-[10px] font-medium text-text-muted px-0.5">History</p>
          {historyTimelineDates.length > 0 ? (
            <MiniCalendar
              dates={historyTimelineDates}
              runKindByDate={portfolioHistoryRunKindByDate}
              selected={effHistoryDate}
              onSelect={selectHistoryDate}
            />
          ) : (
            <div className="glass-card p-4 text-xs text-text-muted">No dated history yet.</div>
          )}
        </div>
        {historyLatestDate && effHistoryDate && effHistoryDate !== historyLatestDate ? (
          <button
            type="button"
            onClick={onClearHistoryDate}
            className="w-full text-xs py-2 rounded-lg border border-border-subtle text-text-secondary hover:text-white hover:bg-white/[0.04] transition-colors"
          >
            Jump to latest ({historyLatestDate})
          </button>
        ) : null}
      </div>

      <div className="flex-1 min-w-0 space-y-10">
        {/* ── Automated pipeline artifacts (Hermes prod path) ──────────────────
            pm_rebalance, risk_debate, deliberation_transcripts are written by
            the automated pipeline but never appear as library docs, so the
            Track-B section below is blank in prod. We surface them here first.
        ──────────────────────────────────────────────────────────────────── */}
        {showPipelineArtifacts && pipe ? (
          <section className="space-y-3">
            <p className="text-[11px] font-semibold text-text-muted tracking-wide">
              Pipeline artifacts
            </p>

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

        {/* ── Track-B analyst session docs (date-scoped library files) ─────────
            In automated prod these are always empty. They appear after an
            analyst has run Track-B phases (market-thesis-exploration, etc.)
            and published docs via the operator interface.
        ──────────────────────────────────────────────────────────────────── */}
        <section className="space-y-3">
          <div className="flex items-center gap-2 px-0.5">
            <Calendar size={15} className="text-fin-amber shrink-0" aria-hidden />
            <span className="text-xs font-medium text-text-muted font-mono">{effHistoryDate ?? '—'}</span>
            {effHistoryDate &&
            pmDocsForHistory.length === 0 &&
            !portfolioDocDates.has(effHistoryDate) &&
            positionHistoryDates.has(effHistoryDate) ? (
              <span className="text-xs text-text-muted ml-2">
                No PM files for this date; position history exists for this snapshot.
              </span>
            ) : null}
          </div>

          {pmDocsForHistory.length === 0 ? (
            // Only show the fallback "no files" card when there are also no
            // pipeline artifacts above — otherwise the tab would look empty.
            !showPipelineArtifacts ? (
              <div className="glass-card px-5 py-10 text-center text-text-muted text-sm">
                No PM files for this date.
              </div>
            ) : null
          ) : (
            (() => {
              const groups = groupPmDocs(pmDocsForHistory);
              return groups.map((group) => {
                const groupKey =
                  group.kind === 'thesis' ? '__thesis__'
                  : group.kind === 'recommendations' ? '__recs__'
                  : group.kind === 'deliberations' ? '__dels__'
                  : '__memo__';
                const groupLabel =
                  group.kind === 'thesis' ? 'Thesis'
                  : group.kind === 'recommendations' ? 'Recommendations'
                  : group.kind === 'deliberations' ? 'Deliberations'
                  : 'PM Memo';
                return (
                  <div key={groupKey} className="glass-card p-0 overflow-hidden">
                    <div className="px-5 py-3 border-b border-border-subtle bg-bg-secondary">
                      <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider">
                        {groupLabel}
                      </h3>
                    </div>
                    <div className="divide-y divide-border-subtle">
                      {group.docs.map((d) => {
                        const active = pmActiveFile?.id === d.id;
                        return (
                          <div key={d.id}>
                            <button
                              type="button"
                              onClick={() => onOpenPmDocument(d)}
                              className={`w-full text-left px-5 py-3 flex items-center gap-3 hover:bg-white/[0.02] transition-colors ${
                                active ? 'bg-fin-amber/5' : ''
                              }`}
                            >
                              <FileText size={14} className="text-fin-amber/70 shrink-0" />
                              <span className="font-mono text-sm">{canonicalPmTitle(d.path)}</span>
                              <span className="ml-auto text-[11px] text-text-muted">{d.phase ?? ''}</span>
                            </button>
                            {active && pmActiveFile ? (
                              <DocumentExpandInline
                                accent="amber"
                                hideTitleBar
                                title={canonicalPmTitle(pmActiveFile.path)}
                                subtitle={pmActiveFile.date ?? null}
                                loading={pmLoading}
                                libraryDoc={pmLibraryDoc}
                              />
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              });
            })()
          )}
        </section>
      </div>
    </div>
  );
}
