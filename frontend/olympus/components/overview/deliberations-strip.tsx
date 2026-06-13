'use client';

import { useState } from 'react';
import Link from 'next/link';
import { MessagesSquare } from 'lucide-react';
import type { PipelineTickerDoc } from '@/lib/types';
import { renderDebateSummaryMarkdown } from '@/lib/render-pipeline-payloads';
import { SafeMarkdown } from '@/components/SafeMarkdown';

/**
 * The "why" behind each conviction move — bull/bear debate summaries the
 * Hermes pipeline now publishes (#699) and bundles into pipeline_observability
 * for the latest run. Full payloads are already in context, so cards render +
 * expand with no extra fetch. Renders null when no deliberations ran.
 */

const STANCE: Record<string, string> = {
  bullish: 'text-fin-green border-fin-green/40 bg-fin-green/10',
  bearish: 'text-fin-red border-fin-red/40 bg-fin-red/10',
  neutral: 'text-fin-blue border-fin-blue/40 bg-fin-blue/10',
};

function s(v: unknown): string {
  return v == null ? '' : String(v);
}

function DebateCard({ doc }: { doc: PipelineTickerDoc }) {
  const [open, setOpen] = useState(false);
  const p = doc.payload ?? {};
  const stance = s(p.net_stance).toLowerCase() || 'neutral';
  const delta = Number(p.conviction_delta ?? 0);
  const deltaStr = `${delta > 0 ? '+' : ''}${delta}`;
  const bull = s(p.bull_thesis).trim();
  const bear = s(p.bear_thesis).trim();

  return (
    <div className="glass-card shrink-0 w-[260px] p-4 flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-sm font-bold text-text-primary">{doc.ticker}</span>
        <span
          className={`rounded-md border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${STANCE[stance] ?? STANCE.neutral}`}
        >
          {stance}
        </span>
      </div>
      <div className="text-[11px] font-mono text-text-muted tabular-nums">
        conviction Δ <span className={delta > 0 ? 'text-fin-green' : delta < 0 ? 'text-fin-red' : ''}>{deltaStr}</span>
      </div>
      {!open && (
        <div className="space-y-1.5 text-xs leading-snug">
          {bull && (
            <p className="text-text-secondary line-clamp-2">
              <span className="text-fin-green font-semibold">Bull:</span> {bull}
            </p>
          )}
          {bear && (
            <p className="text-text-secondary line-clamp-2">
              <span className="text-fin-red font-semibold">Bear:</span> {bear}
            </p>
          )}
        </div>
      )}
      {open && (
        <div className="max-h-72 overflow-y-auto pr-1">
          <SafeMarkdown className="prose-xs">{renderDebateSummaryMarkdown(p)}</SafeMarkdown>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mt-auto text-left text-[10px] font-medium text-fin-blue hover:underline"
      >
        {open ? 'Collapse' : 'Read debate →'}
      </button>
    </div>
  );
}

export function DeliberationsStrip({ transcripts }: { transcripts: PipelineTickerDoc[] }) {
  const debates = (transcripts ?? []).filter(
    (d) => d?.payload && typeof d.payload.net_stance === 'string'
  );
  if (debates.length === 0) return null;

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border-subtle bg-bg-secondary flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessagesSquare size={15} className="text-fin-purple" />
          <h3 className="text-sm font-semibold">Deliberations</h3>
          <span className="text-[10px] text-text-muted">bull vs. bear · {debates.length}</span>
        </div>
        <Link
          href="/portfolio?tab=analysis"
          className="text-[10px] text-fin-blue hover:underline font-medium"
        >
          Full analysis →
        </Link>
      </div>
      <div className="flex gap-3 overflow-x-auto p-4">
        {debates.map((d, i) => (
          <DebateCard key={`${d.ticker}-${i}`} doc={d} />
        ))}
      </div>
    </div>
  );
}
