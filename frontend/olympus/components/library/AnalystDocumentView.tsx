'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cleanMemoProse } from '@/lib/render-pipeline-payloads';

/**
 * Structured view for Hermes per-ticker analyst specialist reports (`analyst/{ticker}`).
 * Real DB shape (documents.payload, 2026-06-17):
 *   { ticker, thesis, stance, conviction_score (integer), sources }
 * Only these 5 keys are rendered — deprecated fields (bull_case, bear_case,
 * entry_criteria, exit_criteria, risks) are never present in live data.
 */

function s(v: unknown): string {
  return v == null ? '' : String(v);
}

function stanceColor(stance: string): string {
  const l = stance.toLowerCase();
  if (l.includes('bull')) return 'text-up';
  if (l.includes('bear')) return 'text-down/90';
  if (l.includes('buy') || l.includes('strong')) return 'text-up';
  if (l.includes('sell') || l.includes('avoid')) return 'text-down';
  return 'text-ink-soft';
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
  // conviction_score is an integer in the real DB payload — convert explicitly.
  const convictionScore =
    payload.conviction_score != null && typeof payload.conviction_score === 'number'
      ? String(payload.conviction_score)
      : '';
  const sources = Array.isArray(payload.sources)
    ? (payload.sources as unknown[]).map((src) => {
        if (src && typeof src === 'object' && !Array.isArray(src)) {
          const o = src as Record<string, unknown>;
          return { title: s(o.title || o.id || 'source').trim(), url: s(o.url).trim() };
        }
        return { title: s(src).trim(), url: '' };
      }).filter((src) => src.title)
    : [];

  // If the payload has no recognizable fields, fall back to markdown render.
  if (!thesis && !stance) {
    return (
      <div className="prose prose-invert max-w-none text-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="space-y-6 text-sm">
      {/* Header: ticker + stance + conviction_score badge */}
      {(ticker || stance) && (
        <div className="flex items-center gap-4 flex-wrap">
          {ticker && (
            <span className="font-mono text-base text-accent font-semibold">{ticker}</span>
          )}
          {stance && (
            <span className={`font-semibold capitalize ${stanceColor(stance)}`}>
              {stance}
              {convictionScore && (
                <span className="ml-2 font-normal text-ink-mute text-xs">
                  conviction: {convictionScore}
                </span>
              )}
            </span>
          )}
        </div>
      )}

      {/* Body: thesis */}
      {thesis && (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Thesis</h3>
          <div className="prose prose-invert max-w-none text-sm text-ink-soft">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanMemoProse(thesis)}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Footer: sources list */}
      {sources.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Sources</h3>
          <ul className="list-disc pl-5 text-ink-soft space-y-1">
            {sources.map((src, i) =>
              src.url ? (
                <li key={i}>
                  <a href={src.url} target="_blank" rel="noopener noreferrer" className="underline hover:text-ink">
                    {src.title}
                  </a>
                </li>
              ) : (
                <li key={i}>{src.title}</li>
              )
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
