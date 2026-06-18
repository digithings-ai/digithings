'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cleanMemoProse } from '@/lib/render-pipeline-payloads';

// ── Legacy deliberation-transcript types ──────────────────────────────────
type FinalRow = {
  ticker?: string;
  analyst_recommendation?: string;
  pm_decision?: string;
  invalidation_condition?: string | null;
};

type Section = { heading?: string; markdown?: string };
// Canonical legacy schema shape: {label, sections[]}
type Round = { label?: string; sections?: Section[] };
// Legacy chat shape (pre-schema): {round, pm, analyst}
type LegacyChatRound = { round?: number; pm?: string; analyst?: string };

/** Convert old {pm, analyst, round} format into canonical {label, sections[]} */
function normalizeLegacyRound(r: LegacyChatRound): Round {
  const label = `Round ${r.round ?? '?'}`;
  const sections: Section[] = [];
  if (r.analyst) sections.push({ heading: 'Analyst', markdown: r.analyst });
  if (r.pm) sections.push({ heading: 'PM', markdown: r.pm });
  return { label, sections };
}

function normalizeRounds(raw: unknown[]): Round[] {
  return raw.map((r) => {
    if (!r || typeof r !== 'object' || Array.isArray(r)) return { label: '—', sections: [] };
    const o = r as Record<string, unknown>;
    // Already canonical
    if (o.label !== undefined || o.sections !== undefined) return o as Round;
    // Legacy chat format
    return normalizeLegacyRound(o as LegacyChatRound);
  });
}

// ── DebateSummary types (automated pipeline) ─────────────────────────────
// { ticker, rounds: [{round_number, bull_argument, bear_argument}],
//   bull_thesis, bear_thesis, net_stance: 'bullish'|'neutral'|'bearish',
//   conviction_delta: int }
type DebateRound = {
  round_number?: number;
  bull_argument?: string;
  bear_argument?: string;
};

/** Colour class keyed on net_stance value */
function stanceClass(stance: string | undefined): string {
  switch (stance) {
    case 'bullish':
      return 'text-fin-green';
    case 'bearish':
      return 'text-fin-red/90';
    default:
      return 'text-text-secondary';
  }
}

export default function DeliberationDocumentView({
  payload,
  fallbackMarkdown,
}: {
  payload: Record<string, unknown> | null;
  fallbackMarkdown: string;
}) {
  // ── RiskDebateSummary shape (risk-debate doc) ─────────────────────────
  // Shape: { aggressive_case, conservative_case, key_tension, net_recommendation? }
  const aggressiveCase =
    payload?.aggressive_case != null && typeof payload.aggressive_case === 'string'
      ? payload.aggressive_case.trim()
      : '';
  const conservativeCase =
    payload?.conservative_case != null && typeof payload.conservative_case === 'string'
      ? payload.conservative_case.trim()
      : '';
  const keyTension =
    payload?.key_tension != null && typeof payload.key_tension === 'string'
      ? payload.key_tension.trim()
      : '';
  const netRecommendation =
    payload?.net_recommendation != null && typeof payload.net_recommendation === 'string'
      ? payload.net_recommendation.trim()
      : '';
  const isRiskDebateShape = aggressiveCase !== '' || conservativeCase !== '' || keyTension !== '';

  // ── DebateSummary shape detection ─────────────────────────────────────
  // The automated pipeline writes the DebateSummary fields directly onto the
  // payload object (not nested under payload.body).
  const debateRounds: DebateRound[] = Array.isArray(payload?.rounds)
    ? (payload.rounds as DebateRound[]).filter(
        (r) =>
          r &&
          typeof r === 'object' &&
          // Bull/bear rounds have bull_argument or bear_argument; legacy rounds have label/sections
          (r.bull_argument !== undefined || r.bear_argument !== undefined || r.round_number !== undefined),
      )
    : [];
  const bullThesis =
    payload?.bull_thesis != null && typeof payload.bull_thesis === 'string' ? payload.bull_thesis.trim() : '';
  const bearThesis =
    payload?.bear_thesis != null && typeof payload.bear_thesis === 'string' ? payload.bear_thesis.trim() : '';
  const netStance =
    payload?.net_stance != null && typeof payload.net_stance === 'string' ? payload.net_stance.trim() : '';
  const convictionDelta =
    payload?.conviction_delta != null ? Number(payload.conviction_delta) : null;
  const debateTicker =
    payload?.ticker != null && typeof payload.ticker === 'string' ? payload.ticker.trim() : '';

  const isDebateShape = debateRounds.length > 0 || bullThesis !== '' || bearThesis !== '' || netStance !== '';

  // ── Legacy deliberation-transcript shape ─────────────────────────────
  const body =
    payload && typeof payload.body === 'object' && payload.body !== null && !Array.isArray(payload.body)
      ? (payload.body as Record<string, unknown>)
      : null;

  const finalDecisions = Array.isArray(body?.final_decisions) ? (body.final_decisions as FinalRow[]) : [];
  const legacyRounds = Array.isArray(body?.rounds) ? normalizeRounds(body.rounds as unknown[]) : [];
  // trigger_summary may be a string (legacy) or array of strings (canonical)
  const triggerSummary = Array.isArray(body?.trigger_summary)
    ? (body.trigger_summary as string[]).filter(Boolean)
    : typeof body?.trigger_summary === 'string' && (body.trigger_summary as string).trim()
      ? [(body.trigger_summary as string).trim()]
      : [];

  // ── Fallback ────────────────────────────────────────────────────────────
  if (!isRiskDebateShape && !isDebateShape && (!body || (!finalDecisions.length && !legacyRounds.length))) {
    return (
      <div className="prose prose-invert max-w-none text-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
      </div>
    );
  }

  // ── RiskDebateSummary rendering (risk-debate doc) ─────────────────────
  if (isRiskDebateShape) {
    return (
      <div className="space-y-8 text-sm">
        <p className="text-[10px] uppercase tracking-widest text-text-muted">Risk temperament debate</p>
        {netRecommendation && (
          <p className="text-text-secondary">
            <span className="font-semibold text-text-primary">Recommendation:</span>{' '}
            {cleanMemoProse(netRecommendation)}
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          {aggressiveCase && (
            <div className="rounded-lg border border-border-subtle bg-bg-secondary/40 p-4">
              <p className="text-[10px] uppercase tracking-wider text-fin-green mb-2">Aggressive case</p>
              <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanMemoProse(aggressiveCase)}</ReactMarkdown>
              </div>
            </div>
          )}
          {conservativeCase && (
            <div className="rounded-lg border border-border-subtle bg-bg-secondary/40 p-4">
              <p className="text-[10px] uppercase tracking-wider text-fin-amber mb-2">Conservative case</p>
              <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanMemoProse(conservativeCase)}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
        {keyTension && (
          <div>
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              Key tension
            </h3>
            <div className="prose prose-invert max-w-none text-sm text-text-secondary">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanMemoProse(keyTension)}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── DebateSummary rendering ──────────────────────────────────────────────
  if (isDebateShape) {
    return (
      <div className="space-y-8 text-sm">
        {/* Header: ticker + net stance */}
        {(debateTicker || netStance) && (
          <div className="flex items-center gap-4 flex-wrap">
            {debateTicker ? (
              <span className="font-mono text-base text-fin-blue font-semibold">{debateTicker}</span>
            ) : null}
            {netStance ? (
              <span className={`font-semibold capitalize ${stanceClass(netStance)}`}>
                {netStance}
                {convictionDelta != null && !Number.isNaN(convictionDelta) ? (
                  <span className="ml-2 text-text-muted font-normal text-xs">
                    Δ{convictionDelta > 0 ? '+' : ''}
                    {convictionDelta}
                  </span>
                ) : null}
              </span>
            ) : null}
          </div>
        )}

        {/* Bull / Bear thesis side-by-side */}
        {(bullThesis || bearThesis) ? (
          <div className="grid gap-4 md:grid-cols-2">
            {bullThesis ? (
              <div className="rounded-lg border border-border-subtle bg-bg-secondary/40 p-4">
                <p className="text-[10px] uppercase tracking-wider text-fin-green mb-2">Bull thesis</p>
                <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanMemoProse(bullThesis)}</ReactMarkdown>
                </div>
              </div>
            ) : null}
            {bearThesis ? (
              <div className="rounded-lg border border-border-subtle bg-bg-secondary/40 p-4">
                <p className="text-[10px] uppercase tracking-wider text-fin-red/90 mb-2">Bear thesis</p>
                <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanMemoProse(bearThesis)}</ReactMarkdown>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        {/* Per-round bull/bear exchange */}
        {debateRounds.length > 0 ? (
          <div>
            <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
              Debate rounds
            </h3>
            <div className="space-y-2">
              {debateRounds.map((r, ri) => (
                <DebateRoundBlock key={ri} round={r} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  // ── Legacy deliberation-transcript rendering ─────────────────────────────
  return (
    <div className="space-y-8 text-sm">
      {triggerSummary.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Triggers</h3>
          <ul className="list-disc pl-5 text-text-secondary space-y-1">
            {triggerSummary.map((t, i) => (
              <li key={i}>{cleanMemoProse(t)}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {finalDecisions.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">
            By asset — analyst vs PM
          </h3>
          <div className="space-y-4">
            {finalDecisions.map((row, i) => (
              <div
                key={i}
                className="rounded-lg border border-border-subtle bg-bg-secondary/40 p-4 space-y-3"
              >
                <div className="font-mono text-base text-fin-blue font-semibold">{row.ticker ?? '—'}</div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-text-muted mb-1">Analyst</p>
                    <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {cleanMemoProse(row.analyst_recommendation || '_—_')}
                      </ReactMarkdown>
                    </div>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-text-muted mb-1">PM decision</p>
                    <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {cleanMemoProse(row.pm_decision || '_—_')}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
                {row.invalidation_condition ? (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-text-muted mb-1">Invalidation</p>
                    <p className="text-text-secondary text-sm whitespace-pre-wrap">
                      {cleanMemoProse(row.invalidation_condition)}
                    </p>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {legacyRounds.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
            Discussion rounds
          </h3>
          <div className="space-y-2">
            {legacyRounds.map((round, ri) => (
              <RoundBlock key={ri} round={round} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ── DebateRoundBlock — bull/bear per-round exchange ──────────────────────
function DebateRoundBlock({ round }: { round: DebateRound }) {
  const [open, setOpen] = useState(true);
  const label = `Round ${round.round_number ?? '?'}`;

  return (
    <div className="rounded-lg border border-border-subtle overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full text-left px-4 py-2 bg-bg-secondary/60 hover:bg-bg-secondary text-sm font-medium"
      >
        {open ? <ChevronDown size={16} className="shrink-0" /> : <ChevronRight size={16} className="shrink-0" />}
        {label}
      </button>
      {open ? (
        <div className="px-4 py-3 grid gap-3 md:grid-cols-2 border-t border-border-subtle">
          <div>
            <h4 className="text-xs font-semibold text-fin-green mb-2">Bull</h4>
            <div className="prose prose-invert max-w-none text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {cleanMemoProse(round.bull_argument || '_—_')}
              </ReactMarkdown>
            </div>
          </div>
          <div>
            <h4 className="text-xs font-semibold text-fin-red/90 mb-2">Bear</h4>
            <div className="prose prose-invert max-w-none text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {cleanMemoProse(round.bear_argument || '_—_')}
              </ReactMarkdown>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ── RoundBlock — legacy {label, sections[]} rounds ───────────────────────
function RoundBlock({ round }: { round: Round }) {
  const [open, setOpen] = useState(true);
  const label = round.label || 'Round';
  const sections = Array.isArray(round.sections) ? round.sections : [];

  return (
    <div className="rounded-lg border border-border-subtle overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full text-left px-4 py-2 bg-bg-secondary/60 hover:bg-bg-secondary text-sm font-medium"
      >
        {open ? <ChevronDown size={16} className="shrink-0" /> : <ChevronRight size={16} className="shrink-0" />}
        {label}
      </button>
      {open ? (
        <div className="px-4 py-3 space-y-4 border-t border-border-subtle">
          {sections.map((sec, si) => (
            <div key={si}>
              {sec.heading ? (
                <h4 className="text-xs font-semibold text-fin-blue/90 mb-2">{sec.heading}</h4>
              ) : null}
              <div className="prose prose-invert max-w-none text-sm">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanMemoProse(sec.markdown || '')}</ReactMarkdown>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
