'use client';

import Link from 'next/link';
import { MessagesSquare } from 'lucide-react';

/**
 * Level-2 disclosure for the Today page: a compact "why today" card that
 * summarizes the reasoning behind the day's move — the net stance of each
 * ticker debate plus the PM memo's one-liner — and links into Why for the full
 * transcript. Renders nothing when neither a debate nor a memo exists, so it
 * never leaves an empty shell on a quiet day.
 */

export interface WhyTodayDebate {
  ticker: string;
  payload?: { net_stance?: unknown; conviction_delta?: unknown } | null;
}

export interface WhyTodayProps {
  deliberations: WhyTodayDebate[];
  pmMemoSummary: string | null;
}

const STANCE_COLOR: Record<string, string> = {
  bullish: 'text-fin-green',
  bearish: 'text-fin-red',
  neutral: 'text-fin-blue',
};

function str(v: unknown): string {
  return v == null ? '' : String(v);
}

export function WhyToday({ deliberations, pmMemoSummary }: WhyTodayProps) {
  const debates = (deliberations ?? []).filter(
    (d) => d?.payload && typeof d.payload.net_stance === 'string'
  );
  if (debates.length === 0 && !pmMemoSummary) return null;

  const chips = debates.slice(0, 4).map((d) => ({
    ticker: d.ticker,
    stance: str(d.payload?.net_stance).toLowerCase() || 'neutral',
  }));

  return (
    <section className="glass-card px-5 py-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <MessagesSquare size={14} className="text-fin-purple" />
          <h2 className="text-xs font-bold uppercase tracking-widest text-text-muted">Why today</h2>
        </div>
        <Link href="/why" className="text-[10px] font-medium text-fin-blue hover:underline">
          {debates.length > 0 ? 'full debate →' : 'the reasoning →'}
        </Link>
      </div>

      {chips.length > 0 ? (
        <p className="text-sm leading-snug text-text-secondary">
          <span className="text-text-muted">
            {debates.length} ticker debate{debates.length !== 1 ? 's' : ''}:{' '}
          </span>
          {chips.map((c, i) => (
            <span key={`${c.ticker}-${i}`}>
              {i > 0 ? ' · ' : ''}
              <span className="font-mono font-semibold text-text-primary">{c.ticker}</span>{' '}
              <span className={STANCE_COLOR[c.stance] ?? STANCE_COLOR.neutral}>{c.stance}</span>
            </span>
          ))}
        </p>
      ) : null}

      {pmMemoSummary ? (
        <p className="mt-2 text-sm leading-snug text-text-secondary">
          <span className="font-semibold text-text-primary">PM:</span> {pmMemoSummary}
        </p>
      ) : null}
    </section>
  );
}
