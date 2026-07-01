'use client';

import Link from 'next/link';
import { Eye, AlertTriangle } from 'lucide-react';
import type { ActionableItem, RiskItem } from '@/lib/types';
import { buildPipelineHref } from '@/lib/pipeline-links';

/**
 * "What to watch" — the always-present read distilled into two ranked lists:
 * the digest's `actionable_summary` (priority → rationale) and its `risk_radar`
 * tail risks (trigger + horizon). Replaces the old, usually-empty "Why today"
 * card. Renders nothing only when the read carried neither — never an empty shell.
 * "See the full read" deep-links to the daily digest node in Pipeline (F2).
 */

export interface WhatToWatchProps {
  actionables: ActionableItem[];
  risks: RiskItem[];
  asOfDate: string | null;
}

export function WhatToWatch({ actionables, risks, asOfDate }: WhatToWatchProps) {
  const acts = actionables.slice(0, 3);
  const tails = risks.slice(0, 2);
  if (acts.length === 0 && tails.length === 0) return null;

  return (
    <section className="glass-card px-5 py-4 sm:px-6">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Eye size={14} className="text-text-muted" />
          <h2 className="text-xs font-bold uppercase tracking-widest text-text-muted">
            What to watch
          </h2>
        </div>
        <Link
          href={buildPipelineHref({ date: asOfDate, stage: 'synthesis', node: 'digest' })}
          className="text-[10px] font-medium text-accent hover:underline"
        >
          see the full read →
        </Link>
      </div>

      {acts.length > 0 ? (
        <ol className="space-y-2.5">
          {acts.map((a, i) => (
            <li key={`${a.label}-${i}`} className="flex gap-3">
              <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-border-subtle font-mono text-[11px] tabular-nums text-text-muted">
                {a.priority ?? i + 1}
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium leading-snug text-text-primary">{a.label}</p>
                {a.rationale ? (
                  <p className="mt-0.5 text-xs leading-snug text-text-secondary">{a.rationale}</p>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      ) : null}

      {tails.length > 0 ? (
        <div className="mt-4 border-t border-border-subtle pt-3">
          <div className="mb-2 flex items-center gap-2">
            <AlertTriangle size={12} className="text-fin-amber" />
            <h3 className="text-[10px] font-bold uppercase tracking-widest text-text-muted">
              Tail risks
            </h3>
          </div>
          <ul className="space-y-2">
            {tails.map((r, i) => (
              <li key={`${r.label}-${i}`} className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm leading-snug text-text-secondary">
                    <span className="font-medium text-text-primary">{r.label}</span>
                    {r.trigger ? <span className="text-text-muted"> — {r.trigger}</span> : null}
                  </p>
                </div>
                {r.horizonHours != null ? (
                  <span className="shrink-0 font-mono text-[10px] tabular-nums text-fin-amber">
                    {r.horizonHours}h
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
