'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Structured view for Hermes per-ticker analyst specialist reports (`analyst/{ticker}`).
 * The pipeline writes a SpecialistPayload with shape:
 *   { ticker, thesis, stance, conviction, bull_case, bear_case,
 *     entry_criteria, exit_criteria, risks, sources }
 * All fields are optional — renders gracefully when any are absent.
 */

function s(v: unknown): string {
  return v == null ? '' : String(v);
}

function stanceColor(stance: string): string {
  const l = stance.toLowerCase();
  if (l.includes('bull')) return 'text-fin-green';
  if (l.includes('bear')) return 'text-fin-red/90';
  if (l.includes('buy') || l.includes('strong')) return 'text-fin-green';
  if (l.includes('sell') || l.includes('avoid')) return 'text-fin-red';
  return 'text-text-secondary';
}

export default function AnalystDocumentView({
  payload,
  fallbackMarkdown,
}: {
  payload: Record<string, unknown> | null;
  fallbackMarkdown: string;
}) {
  if (!payload) {
    return (
      <div className="prose prose-invert max-w-none text-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
      </div>
    );
  }

  const ticker = s(payload.ticker).trim();
  const thesis = s(payload.thesis).trim();
  const stance = s(payload.stance).trim();
  const conviction = s(payload.conviction).trim();
  const bull = s(payload.bull_case).trim();
  const bear = s(payload.bear_case).trim();
  const entry = s(payload.entry_criteria).trim();
  const exit = s(payload.exit_criteria).trim();
  const risks = Array.isArray(payload.risks) ? (payload.risks as unknown[]).map((r) => s(r).trim()).filter(Boolean) : [];

  // If the payload has no recognizable fields, fall back to markdown render.
  if (!thesis && !stance && !bull && !bear) {
    return (
      <div className="prose prose-invert max-w-none text-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="space-y-6 text-sm">
      {/* Header row */}
      {(ticker || stance) && (
        <div className="flex items-center gap-4 flex-wrap">
          {ticker && (
            <span className="font-mono text-base text-fin-blue font-semibold">{ticker}</span>
          )}
          {stance && (
            <span className={`font-semibold capitalize ${stanceColor(stance)}`}>
              {stance}
              {conviction && (
                <span className="ml-2 font-normal text-text-muted text-xs">
                  conviction: {conviction}
                </span>
              )}
            </span>
          )}
        </div>
      )}

      {/* Thesis */}
      {thesis && (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Thesis</h3>
          <div className="prose prose-invert max-w-none text-sm text-text-secondary">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{thesis}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Bull / Bear side-by-side */}
      {(bull || bear) && (
        <div className="grid gap-4 md:grid-cols-2">
          {bull && (
            <div className="rounded-lg border border-border-subtle bg-bg-secondary/40 p-4">
              <p className="text-[10px] uppercase tracking-wider text-fin-green mb-2">Bull case</p>
              <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{bull}</ReactMarkdown>
              </div>
            </div>
          )}
          {bear && (
            <div className="rounded-lg border border-border-subtle bg-bg-secondary/40 p-4">
              <p className="text-[10px] uppercase tracking-wider text-fin-red/90 mb-2">Bear case</p>
              <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{bear}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Entry / Exit criteria */}
      {(entry || exit) && (
        <div className="grid gap-4 md:grid-cols-2">
          {entry && (
            <div>
              <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                Entry criteria
              </h3>
              <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{entry}</ReactMarkdown>
              </div>
            </div>
          )}
          {exit && (
            <div>
              <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                Exit criteria
              </h3>
              <div className="prose prose-invert max-w-none text-sm text-text-secondary">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{exit}</ReactMarkdown>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Risks */}
      {risks.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Risks</h3>
          <ul className="list-disc pl-5 text-text-secondary space-y-1">
            {risks.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
