'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { isEvolutionSourcesEmpty } from '@/lib/library-doc-tier';

type Rating = { name?: string; reliability?: string; notes?: string };

export default function EvolutionSourcesDocumentView({
  payload,
  fallbackMarkdown,
}: {
  payload: Record<string, unknown> | null;
  fallbackMarkdown: string;
}) {
  if (!payload || isEvolutionSourcesEmpty(payload)) {
    return (
      <div className="rounded-lg border border-dashed border-border-subtle bg-bg-secondary/30 p-6 text-center text-text-muted text-sm">
        <p className="font-medium text-text-secondary mb-1">Draft — no source ratings yet</p>
        <p className="text-xs">
          This outline was published without scores. Open the Evolution tab when the scorecard is filled in, or view raw
          markdown below.
        </p>
        <div className="mt-4 prose prose-invert max-w-none text-left text-sm opacity-80">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
        </div>
      </div>
    );
  }

  const p = payload;
  const date = String(p.date || '');
  const title = String(p.title || 'Sources');
  const body =
    typeof p.body === 'object' && p.body !== null && !Array.isArray(p.body)
      ? (p.body as Record<string, unknown>)
      : {};
  const notes = String(body.notes || '');
  const ratings = Array.isArray(body.source_ratings) ? (body.source_ratings as Rating[]) : [];

  return (
    <div className="space-y-6 text-sm">
      <div>
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        {date ? <p className="text-xs text-text-muted font-mono mt-1">{date}</p> : null}
      </div>
      {notes ? (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Notes</h3>
          <div className="prose prose-invert max-w-none text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{notes}</ReactMarkdown>
          </div>
        </div>
      ) : null}
      <div>
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Ratings</h3>
        <ul className="space-y-3">
          {ratings.map((r, i) => (
            <li key={i} className="rounded-md border border-border-subtle bg-bg-secondary/40 p-3">
              <p className="font-medium text-fin-blue">
                {r.name ?? '—'}{' '}
                {r.reliability ? (
                  <span className="text-text-muted font-normal text-xs">({r.reliability})</span>
                ) : null}
              </p>
              {r.notes ? <p className="text-text-secondary text-sm mt-1 whitespace-pre-wrap">{r.notes}</p> : null}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
