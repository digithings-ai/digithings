'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { SafeMarkdown } from '@/components/SafeMarkdown';
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
      return 'text-up';
    case 'bearish':
      return 'text-down/90';
    default:
      return 'text-ink-soft';
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

  // ── H6 DeliberationSummary fields (#1679) ─────────────────────────────
  // PM↔analyst deliberations carry {transcript:[{role,round_number,message}],
  // conclusion, converged, carried, escalated, cap_reason} — none of which the
  // bull/bear branch rendered, so H6 docs lost their transcript entirely.
  const conclusion =
    payload?.conclusion != null && typeof payload.conclusion === 'string'
      ? payload.conclusion.trim()
      : '';
  const carried = payload?.carried === true;
  const escalated = payload?.escalated === true;
  const capReason =
    payload?.cap_reason != null && typeof payload.cap_reason === 'string'
      ? payload.cap_reason.trim()
      : '';
  const converged = typeof payload?.converged === 'boolean' ? payload.converged : null;
  const transcript: { role?: string; round_number?: number; message?: string }[] = Array.isArray(
    payload?.transcript,
  )
    ? (payload.transcript as { role?: string; round_number?: number; message?: string }[]).filter(
        (turn) => turn && typeof turn.message === 'string' && turn.message.trim() !== '',
      )
    : [];

  const isDebateShape =
    debateRounds.length > 0 ||
    bullThesis !== '' ||
    bearThesis !== '' ||
    netStance !== '' ||
    transcript.length > 0 ||
    conclusion !== '';

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
      <SafeMarkdown>{fallbackMarkdown}</SafeMarkdown>
    );
  }

  // ── RiskDebateSummary rendering (risk-debate doc) ─────────────────────
  if (isRiskDebateShape) {
    return (
      <div className="space-y-8 text-sm">
        <p className="text-[10px] uppercase tracking-widest text-ink-mute">Risk temperament debate</p>
        {netRecommendation && (
          <p className="text-ink-soft">
            <span className="font-semibold text-ink">Recommendation:</span>{' '}
            {cleanMemoProse(netRecommendation)}
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          {aggressiveCase && (
            <div className="rounded-lg border border-hair bg-term-bg/40 p-4">
              <p className="text-[10px] uppercase tracking-wider text-up mb-2">Aggressive case</p>
              <SafeMarkdown>{cleanMemoProse(aggressiveCase)}</SafeMarkdown>
            </div>
          )}
          {conservativeCase && (
            <div className="rounded-lg border border-hair bg-term-bg/40 p-4">
              <p className="text-[10px] uppercase tracking-wider text-warn mb-2">Conservative case</p>
              <SafeMarkdown>{cleanMemoProse(conservativeCase)}</SafeMarkdown>
            </div>
          )}
        </div>
        {keyTension && (
          <div>
            <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">
              Key tension
            </h3>
            <SafeMarkdown>{cleanMemoProse(keyTension)}</SafeMarkdown>
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
              <span className="font-mono text-base text-accent font-semibold">{debateTicker}</span>
            ) : null}
            {netStance ? (
              <span className={`font-semibold capitalize ${stanceClass(netStance)}`}>
                {netStance}
                {convictionDelta != null && !Number.isNaN(convictionDelta) ? (
                  <span className="ml-2 text-ink-mute font-normal text-xs">
                    Δ{convictionDelta > 0 ? '+' : ''}
                    {convictionDelta}
                  </span>
                ) : null}
              </span>
            ) : null}
          </div>
        )}

        {/* H6 state badges (#1679): carried / converged / max_rounds escalation */}
        {(carried || escalated || converged != null) && (
          <div className="flex flex-wrap items-center gap-2">
            {carried && (
              <span className="rounded border border-hair px-2 py-0.5 font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
                carried from prior run
              </span>
            )}
            {converged === true && !carried && (
              <span className="rounded border border-hair px-2 py-0.5 font-mono text-[0.6rem] uppercase tracking-[0.08em] text-up">
                converged
              </span>
            )}
            {escalated && (
              <span className="rounded border border-hair px-2 py-0.5 font-mono text-[0.6rem] uppercase tracking-[0.08em] text-warn">
                escalated{capReason ? ` · ${capReason}` : ''}
              </span>
            )}
          </div>
        )}

        {/* H6 conclusion — the deliberation's final read */}
        {conclusion && (
          <div>
            <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">
              Conclusion
            </h3>
            <SafeMarkdown>{cleanMemoProse(conclusion)}</SafeMarkdown>
          </div>
        )}

        {/* Bull / Bear thesis side-by-side */}
        {(bullThesis || bearThesis) ? (
          <div className="grid gap-4 md:grid-cols-2">
            {bullThesis ? (
              <div className="rounded-lg border border-hair bg-term-bg/40 p-4">
                <p className="text-[10px] uppercase tracking-wider text-up mb-2">Bull thesis</p>
                <SafeMarkdown>{cleanMemoProse(bullThesis)}</SafeMarkdown>
              </div>
            ) : null}
            {bearThesis ? (
              <div className="rounded-lg border border-hair bg-term-bg/40 p-4">
                <p className="text-[10px] uppercase tracking-wider text-down/90 mb-2">Bear thesis</p>
                <SafeMarkdown>{cleanMemoProse(bearThesis)}</SafeMarkdown>
              </div>
            ) : null}
          </div>
        ) : null}

        {/* Per-round bull/bear exchange */}
        {debateRounds.length > 0 ? (
          <div>
            <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">
              Debate rounds
            </h3>
            <div className="space-y-2">
              {debateRounds.map((r, ri) => (
                <DebateRoundBlock key={ri} round={r} />
              ))}
            </div>
          </div>
        ) : null}

        {/* PM ↔ analyst transcript, grouped by round (#1679) */}
        {transcript.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">
              Deliberation transcript
            </h3>
            <ol className="space-y-3">
              {transcript.map((turn, i) => (
                <li key={i} className="rounded-lg border border-hair bg-term-bg/40 p-4">
                  <p className="mb-1.5 flex items-center gap-2 font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
                    <span>Round {turn.round_number ?? '?'}</span>
                    <span className={turn.role === 'pm' ? 'text-accent' : 'text-ink-soft'}>
                      {turn.role === 'pm' ? 'PM challenge' : 'Analyst response'}
                    </span>
                  </p>
                  <SafeMarkdown>{cleanMemoProse(turn.message ?? '')}</SafeMarkdown>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    );
  }

  // ── Legacy deliberation-transcript rendering ─────────────────────────────
  return (
    <div className="space-y-8 text-sm">
      {triggerSummary.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Triggers</h3>
          <ul className="list-disc pl-5 text-ink-soft space-y-1">
            {triggerSummary.map((t, i) => (
              <li key={i}>{cleanMemoProse(t)}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {finalDecisions.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-3">
            By asset — analyst vs PM
          </h3>
          <div className="space-y-4">
            {finalDecisions.map((row, i) => (
              <div
                key={i}
                className="rounded-lg border border-hair bg-term-bg/40 p-4 space-y-3"
              >
                <div className="font-mono text-base text-accent font-semibold">{row.ticker ?? '—'}</div>
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-ink-mute mb-1">Analyst</p>
                    <SafeMarkdown>{cleanMemoProse(row.analyst_recommendation || '_—_')}</SafeMarkdown>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-ink-mute mb-1">PM decision</p>
                    <SafeMarkdown>{cleanMemoProse(row.pm_decision || '_—_')}</SafeMarkdown>
                  </div>
                </div>
                {row.invalidation_condition ? (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-ink-mute mb-1">Invalidation</p>
                    <p className="text-ink-soft text-sm whitespace-pre-wrap">
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
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">
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
    <div className="rounded-lg border border-hair overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full text-left px-4 py-2 bg-term-bg/60 hover:bg-term-bg text-sm font-medium"
      >
        {open ? <ChevronDown size={16} className="shrink-0" /> : <ChevronRight size={16} className="shrink-0" />}
        {label}
      </button>
      {open ? (
        <div className="px-4 py-3 grid gap-3 md:grid-cols-2 border-t border-hair">
          <div>
            <h4 className="text-xs font-semibold text-up mb-2">Bull</h4>
            <SafeMarkdown>{cleanMemoProse(round.bull_argument || '_—_')}</SafeMarkdown>
          </div>
          <div>
            <h4 className="text-xs font-semibold text-down/90 mb-2">Bear</h4>
            <SafeMarkdown>{cleanMemoProse(round.bear_argument || '_—_')}</SafeMarkdown>
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
    <div className="rounded-lg border border-hair overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full text-left px-4 py-2 bg-term-bg/60 hover:bg-term-bg text-sm font-medium"
      >
        {open ? <ChevronDown size={16} className="shrink-0" /> : <ChevronRight size={16} className="shrink-0" />}
        {label}
      </button>
      {open ? (
        <div className="px-4 py-3 space-y-4 border-t border-hair">
          {sections.map((sec, si) => (
            <div key={si}>
              {sec.heading ? (
                <h4 className="text-xs font-semibold text-accent/90 mb-2">{sec.heading}</h4>
              ) : null}
              <SafeMarkdown>{cleanMemoProse(sec.markdown || '')}</SafeMarkdown>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
