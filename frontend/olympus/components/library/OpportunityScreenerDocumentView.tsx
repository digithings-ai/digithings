'use client';

import { SafeMarkdown } from '@/components/SafeMarkdown';

/** Loose row shape for opportunity_screen / screener JSON variants. */
type ScoreRow = Record<string, unknown>;

function pickRows(body: Record<string, unknown>): ScoreRow[] {
  const candidates = ['universe_scores', 'ranked_universe', 'shortlist', 'candidates', 'rows', 'scores'];
  for (const k of candidates) {
    const v = body[k];
    if (Array.isArray(v) && v.length && typeof v[0] === 'object' && v[0] !== null) {
      return v as ScoreRow[];
    }
  }
  return [];
}

function str(v: unknown): string {
  if (v == null) return '—';
  return String(v);
}

function num(v: unknown): string {
  if (v == null || Number.isNaN(Number(v))) return '—';
  return Number(v).toFixed(1);
}

export default function OpportunityScreenerDocumentView({
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

  const rows = body ? pickRows(body) : [];
  const summary = body?.summary != null ? String(body.summary).trim() : '';
  const regimeNote = body?.regime_note != null ? String(body.regime_note).trim() : '';

  if (!body || (!rows.length && !summary)) {
    return (
      <SafeMarkdown>{fallbackMarkdown}</SafeMarkdown>
    );
  }

  const columns = rows.length
    ? Array.from(
        rows.reduce((acc, row) => {
          for (const k of Object.keys(row)) {
            if (k === 'notes' || k === 'rationale') continue;
            acc.add(k);
          }
          return acc;
        }, new Set<string>())
      ).slice(0, 12)
    : [];

  return (
    <div className="space-y-6 text-sm">
      {summary ? (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Summary</h3>
          <SafeMarkdown>{summary}</SafeMarkdown>
        </div>
      ) : null}
      {regimeNote ? (
        <div className="rounded-lg border border-hair bg-term-bg/50 p-3 text-ink-soft text-xs">
          <span className="text-ink-mute uppercase tracking-wider mr-2">Regime</span>
          {regimeNote}
        </div>
      ) : null}
      {rows.length > 0 && columns.length > 0 ? (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-3">Universe scores</h3>
          <div className="overflow-x-auto rounded-lg border border-hair">
            <table className="w-full text-xs min-w-[480px]">
              <thead>
                <tr className="text-ink-mute text-left border-b border-hair bg-term-bg/80">
                  {columns.map((c) => (
                    <th key={c} className="px-2 py-2 font-medium capitalize whitespace-nowrap">
                      {c.replace(/_/g, ' ')}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-hair">
                {rows.map((row, i) => (
                  <tr key={i} className="hover:bg-ink/[0.02]">
                    {columns.map((c) => {
                      const v = row[c];
                      const isNum =
                        typeof v === 'number' ||
                        (typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v)));
                      return (
                        <td key={c} className="px-2 py-1.5 text-ink-soft max-w-[220px] truncate" title={str(v)}>
                          {isNum ? num(v) : str(v)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
      {body.notes != null && String(body.notes).trim() ? (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Notes</h3>
          <SafeMarkdown>{String(body.notes)}</SafeMarkdown>
        </div>
      ) : null}
    </div>
  );
}
