'use client';

import { useEffect, useMemo, useState } from 'react';
import { SafeMarkdown } from '@/components/SafeMarkdown';
import { isSupabaseConfigured, supabase } from '@/lib/supabase';
import {
  actionForRow,
  buildPmActionContext,
  formatPmConfidence,
  labelPmAction,
  parsePmDirectionMemo,
  sortPmRoster,
  type PmAction,
  type PmActionContext,
  type PmDirection,
} from '@/lib/pm-direction-view';

function actionClass(action: PmAction): string {
  switch (action) {
    case 'buy':
      return 'text-up';
    case 'sell':
      return 'text-down/90';
    case 'hold':
      return 'text-ink-soft';
    case 'long':
    case 'flat':
      return 'text-ink-mute';
    default: {
      const _exhaustive: never = action;
      return _exhaustive;
    }
  }
}

function rosterFromPayload(payload: unknown): Array<{ ticker: string; direction: string }> {
  const parsed = parsePmDirectionMemo(payload);
  return parsed.roster.map((row) => ({ ticker: row.ticker, direction: row.direction }));
}

async function fetchPmDirectionActionContext(docDate: string): Promise<PmActionContext> {
  if (!isSupabaseConfigured() || !supabase || !docDate) {
    return buildPmActionContext({});
  }

  const [rebalanceRes, priorRes] = await Promise.all([
    supabase
      .from('documents')
      .select('payload')
      .eq('document_key', 'pm-rebalance')
      .eq('date', docDate)
      .order('id', { ascending: false })
      .limit(1),
    supabase
      .from('documents')
      .select('payload')
      .eq('document_key', 'pm-direction-memo')
      .lt('date', docDate)
      .order('date', { ascending: false })
      .limit(1),
  ]);

  // Promise.all unifies the two Postgrest builders so `.data` collapses to
  // `never`; pin the documents.payload row the same way queries.ts does.
  type PayloadRow = { payload: unknown };
  const rebalanceRow = (rebalanceRes.data as PayloadRow[] | null)?.[0]?.payload;
  const rebalance =
    rebalanceRow && typeof rebalanceRow === 'object' && !Array.isArray(rebalanceRow)
      ? (rebalanceRow as Record<string, unknown>)
      : null;
  const priorPayload = (priorRes.data as PayloadRow[] | null)?.[0]?.payload;
  return buildPmActionContext({
    priorRoster: rosterFromPayload(priorPayload),
    rebalance,
  });
}

export default function PmDirectionDocumentView({
  payload,
  fallbackMarkdown,
  docDate,
  priorRoster,
  rebalance,
}: {
  payload: Record<string, unknown> | null;
  fallbackMarkdown: string;
  docDate?: string;
  priorRoster?: Array<{ ticker: string; direction: PmDirection | string }>;
  rebalance?: Record<string, unknown> | null;
}) {
  const parsed = useMemo(() => parsePmDirectionMemo(payload), [payload]);
  const injected = priorRoster !== undefined || rebalance !== undefined;
  const [fetched, setFetched] = useState<PmActionContext | null>(null);

  useEffect(() => {
    if (injected || !docDate) return;
    let cancelled = false;
    void (async () => {
      const ctx = await fetchPmDirectionActionContext(docDate);
      if (!cancelled) setFetched(ctx);
    })();
    return () => {
      cancelled = true;
    };
  }, [injected, docDate]);

  const context = useMemo(() => {
    if (injected) {
      return buildPmActionContext({ priorRoster, rebalance });
    }
    return fetched ?? buildPmActionContext({});
  }, [injected, priorRoster, rebalance, fetched]);

  if (!parsed.roster.length && !parsed.memo) {
    return <SafeMarkdown>{fallbackMarkdown}</SafeMarkdown>;
  }

  const rows = sortPmRoster(parsed.roster);
  const headingDate = parsed.date || docDate || null;

  return (
    <div className="space-y-6 text-sm" data-testid="pm-direction-document-view">
      <div>
        <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">
          PM direction
        </h3>
        {headingDate ? (
          <p className="font-mono text-xs text-ink-mute mb-3">{headingDate}</p>
        ) : null}
        {parsed.memo ? (
          <p className="text-ink leading-relaxed whitespace-pre-wrap">{parsed.memo}</p>
        ) : null}
      </div>

      {rows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-hair text-ink-mute">
                <th className="py-2 pr-3 font-medium">Ticker</th>
                <th className="py-2 pr-3 font-medium">Action</th>
                <th className="py-2 pr-3 font-medium text-right">Rank</th>
                <th className="py-2 pr-3 font-medium text-right">Confidence</th>
                <th className="py-2 font-medium">Narrative</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const action = actionForRow(row, context);
                return (
                  <tr key={row.ticker} className="border-b border-hair/60 align-top">
                    <td className="py-2 pr-3 font-mono text-accent">{row.ticker}</td>
                    <td className={`py-2 pr-3 font-medium ${actionClass(action)}`}>
                      {labelPmAction(action)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">{row.convictionRank}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {formatPmConfidence(row.confidence)}
                    </td>
                    <td className="py-2 text-ink-soft whitespace-pre-wrap">
                      {row.narrative ?? '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
