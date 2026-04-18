'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, ChevronRight } from 'lucide-react';

type FinalRow = {
  ticker?: string;
  analyst_recommendation?: string;
  pm_decision?: string;
  invalidation_condition?: string | null;
};

type Section = { heading?: string; markdown?: string };
// Canonical schema shape: {label, sections[]}
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

export default function DeliberationDocumentView({
  payload,
  fallbackMarkdown,
}: {
  payload: Record<string, unknown> | null;
  fallbackMarkdown: string;
}) {
  const body =
    payload && typeof payload.body === 'object' && payload.body !== null && !Array.isArray(payload.body)
      ? (payload.body as Record<string, unknown>)
      : null;

  const finalDecisions = Array.isArray(body?.final_decisions) ? (body.final_decisions as FinalRow[]) : [];
  const rounds = Array.isArray(body?.rounds) ? normalizeRounds(body.rounds as unknown[]) : [];
  // trigger_summary may be a string (legacy) or array of strings (canonical)
  const triggerSummary = Array.isArray(body?.trigger_summary)
    ? (body.trigger_summary as string[]).filter(Boolean)
    : typeof body?.trigger_summary === 'string' && (body.trigger_summary as string).trim()
      ? [(body.trigger_summary as string).trim()]
      : [];

  if (!body || (!finalDecisions.length && !rounds.length)) {
    return (
      <div className="prose prose-invert max-w-none text-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="space-y-8 text-sm">
      {triggerSummary.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Triggers</h3>
          <ul className="list-disc pl-5 text-text-secondary space-y-1">
            {triggerSummary.map((t, i) => (
              <li key={i}>{t}</li>
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
                        {row.analyst_recommendation || '_—_'}
                      </ReactMarkdown>
                    </div>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-text-muted mb-1">PM decision</p>
                    <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{row.pm_decision || '_—_'}</ReactMarkdown>
                    </div>
                  </div>
                </div>
                {row.invalidation_condition ? (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-text-muted mb-1">Invalidation</p>
                    <p className="text-text-secondary text-sm whitespace-pre-wrap">{row.invalidation_condition}</p>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {rounds.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
            Discussion rounds
          </h3>
          <div className="space-y-2">
            {rounds.map((round, ri) => (
              <RoundBlock key={ri} round={round} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

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
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{sec.markdown || ''}</ReactMarkdown>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
