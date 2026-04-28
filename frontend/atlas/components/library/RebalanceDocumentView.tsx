'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

type Row = {
  ticker?: string;
  current_pct?: number | null;
  recommended_pct?: number | null;
  change_pct?: number | null;
  action?: string;
  urgency?: string;
  rationale?: string;
};

function pct(n: unknown): string {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return `${Number(n).toFixed(2)}%`;
}

export default function RebalanceDocumentView({
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
  const table = body?.rebalance_table;
  const rows: Row[] = Array.isArray(table) ? (table as Row[]) : [];
  const pmNotes = body?.pm_notes != null ? String(body.pm_notes) : '';
  const deltaSummary = body?.delta_summary;
  const ds =
    deltaSummary && typeof deltaSummary === 'object' && !Array.isArray(deltaSummary)
      ? (deltaSummary as Record<string, unknown>)
      : null;

  if (!rows.length && !pmNotes) {
    return (
      <div className="prose prose-invert max-w-none text-sm">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{fallbackMarkdown}</ReactMarkdown>
      </div>
    );
  }

  return (
    <div className="space-y-6 text-sm">
      {ds && (
        <div className="rounded-lg border border-border-subtle bg-bg-secondary/50 p-4 space-y-1 text-text-secondary">
          <p className="text-xs font-semibold text-text-muted uppercase tracking-wider">Delta summary</p>
          <p>
            Changes triggered: <span className="text-white">{String(ds.changes_triggered ?? '—')}</span> · Held:{' '}
            <span className="text-white">{String(ds.held_count ?? '—')}</span>
          </p>
          {ds.largest_move != null && String(ds.largest_move).trim() ? (
            <p>
              Largest move: <span className="text-white">{String(ds.largest_move)}</span>
            </p>
          ) : null}
          {Array.isArray(ds.new_entries) && ds.new_entries.length > 0 ? (
            <p>
              New: <span className="text-fin-blue">{ds.new_entries.join(', ')}</span>
            </p>
          ) : null}
          {Array.isArray(ds.exits) && ds.exits.length > 0 ? (
            <p>
              Exits: <span className="text-fin-red/90">{ds.exits.join(', ')}</span>
            </p>
          ) : null}
        </div>
      )}

      {pmNotes ? (
        <div>
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">PM notes</h3>
          <div className="prose prose-invert max-w-none text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{pmNotes}</ReactMarkdown>
          </div>
        </div>
      ) : null}

      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">Rebalance table</h3>
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-border-subtle text-text-muted">
                <th className="py-2 pr-3 font-medium">Ticker</th>
                <th className="py-2 pr-3 font-medium text-right">Current</th>
                <th className="py-2 pr-3 font-medium text-right">Target</th>
                <th className="py-2 pr-3 font-medium text-right">Δ</th>
                <th className="py-2 pr-3 font-medium">Action</th>
                <th className="py-2 pr-3 font-medium">Urgency</th>
                <th className="py-2 font-medium">Rationale</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-border-subtle/60 align-top">
                  <td className="py-2 pr-3 font-mono text-fin-blue">{r.ticker ?? '—'}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{pct(r.current_pct)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{pct(r.recommended_pct)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{pct(r.change_pct)}</td>
                  <td className="py-2 pr-3">{r.action ?? '—'}</td>
                  <td className="py-2 pr-3">{r.urgency ?? '—'}</td>
                  <td className="py-2 text-text-secondary whitespace-pre-wrap">{r.rationale ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
