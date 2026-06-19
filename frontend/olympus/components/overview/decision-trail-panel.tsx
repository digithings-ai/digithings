'use client';

import Link from 'next/link';
import type { Route } from 'next';
import { Footprints, MessagesSquare, ClipboardList, FileText, Scale } from 'lucide-react';
import type { PipelineTickerDoc } from '@/lib/types';

/**
 * The day's decision artifacts as a navigable trail — the read path from
 * "what the pipeline decided" into the full documents. Resurrects the dead
 * pmQuickLinks/latestRunDocByKey scaffolding that page.tsx computed but never
 * rendered. Honest empty state naming the last run date.
 */

export interface DecisionTrailProps {
  latestDate: string | null;
  deliberations: PipelineTickerDoc[];
  hasPmMemo: boolean;
  hasDigest: boolean;
  /** Phase C PR1b wires the risk-debate fetch; until then this is false. */
  hasRiskDebate?: boolean;
}

interface TrailRow {
  icon: typeof FileText;
  label: string;
  detail: string;
  href: Route;
}

export function DecisionTrailPanel({
  latestDate,
  deliberations,
  hasPmMemo,
  hasDigest,
  hasRiskDebate = false,
}: DecisionTrailProps) {
  const rows: TrailRow[] = [];

  if (deliberations.length > 0) {
    const tickers = deliberations
      .map((d) => d.ticker)
      .filter(Boolean)
      .slice(0, 6)
      .join(', ');
    rows.push({
      icon: MessagesSquare,
      label: 'Deliberations',
      detail: `${deliberations.length} ticker${deliberations.length !== 1 ? 's' : ''}${tickers ? ` · ${tickers}` : ''}`,
      href: '/portfolio?tab=analysis' as Route,
    });
  }
  if (hasPmMemo) {
    rows.push({
      icon: ClipboardList,
      label: 'PM allocation memo',
      detail: 'Rationale behind the target book',
      href: '/portfolio?tab=analysis' as Route,
    });
  }
  if (hasRiskDebate) {
    rows.push({
      icon: Scale,
      label: 'Risk debate',
      detail: 'Aggressive vs. conservative framing',
      href: '/portfolio?tab=analysis' as Route,
    });
  }
  if (hasDigest) {
    rows.push({
      icon: FileText,
      label: 'Daily digest',
      detail: 'Full narrative research report',
      href: '/research?tab=daily' as Route,
    });
  }

  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border-subtle bg-bg-secondary flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Footprints size={15} className="text-fin-amber" />
          <h3 className="text-sm font-semibold">Decision trail</h3>
        </div>
        {latestDate && (
          <span className="text-[10px] text-text-muted font-mono">as of {latestDate}</span>
        )}
      </div>

      {rows.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-text-muted">
          {latestDate
            ? `No decision artifacts published for ${latestDate} yet — they appear after the next pipeline run.`
            : 'Decision artifacts appear after the first pipeline run.'}
        </p>
      ) : (
        <div className="divide-y divide-border-subtle">
          {rows.map((r) => {
            const Icon = r.icon;
            return (
              <Link
                key={r.label}
                href={r.href}
                className="flex items-center gap-3 px-5 py-3 hover:bg-white/[0.025] transition-colors group"
              >
                <Icon size={15} className="text-text-muted group-hover:text-fin-blue transition-colors shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-text-primary">{r.label}</div>
                  <div className="line-clamp-2 text-xs leading-snug text-text-muted" title={r.detail}>
                    {r.detail}
                  </div>
                </div>
                <span className="text-fin-blue/60 group-hover:text-fin-blue text-xs shrink-0">→</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
