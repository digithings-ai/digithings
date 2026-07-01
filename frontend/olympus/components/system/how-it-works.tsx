'use client';

import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { SectionCard } from '@/components/observability/shared';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { OperatorControls } from './operator-controls';

const PERSISTS: { what: string; where: string; note: string }[] = [
  { what: 'Research segments', where: 'documents', note: 'One row per segment (alt-data, macro, sectors, asset classes)' },
  { what: 'Daily digest', where: 'documents + daily_snapshots', note: 'The read — headline, regime bias, digest markdown' },
  { what: 'Analyst & deliberation notes', where: 'documents', note: 'Per-ticker analyst verdicts and PM⇄analyst debates' },
  { what: 'Portfolio decisions', where: 'positions + decision_log', note: 'The booked book and each signed call with its thesis' },
  { what: 'Run diagnostics', where: 'atlas_run_health', note: 'Run status, segment counts, timing (public view; cost/tokens operator-only)' },
];

export function HowItWorks() {
  return (
    <div className="space-y-6">
      <SectionCard title="How it works">
        <p className="max-w-3xl text-sm leading-relaxed text-text-secondary">
          Each run, <span className="text-text-primary">Atlas</span> researches the market across
          parallel phases — alternative data, institutional flows, macro, asset classes, and sectors —
          and synthesizes a daily read. <span className="text-text-primary">Hermes</span> then
          deliberates: it frames theses, screens candidates, runs per-ticker analysts and PM⇄analyst
          debates, and sizes risk. The result is a booked portfolio with a signed decision behind every
          position.
        </p>
        <Link
          href={buildPipelineHref({})}
          className="inline-flex items-center gap-1.5 text-sm text-[var(--accent)] hover:underline"
        >
          See the full graph
          <ArrowRight size={14} />
        </Link>
      </SectionCard>

      <SectionCard
        title="What a run persists"
        subtitle="Every run is durable — these are the tables it writes, the source of truth the dashboard reads."
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left text-xs text-text-muted">
                <th className="py-2 pr-4 font-medium">What</th>
                <th className="py-2 pr-4 font-medium">Where</th>
                <th className="py-2 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody>
              {PERSISTS.map((r) => (
                <tr key={r.what} className="border-b border-border-subtle/50">
                  <td className="py-2 pr-4 text-text-primary">{r.what}</td>
                  <td className="py-2 pr-4 font-mono text-xs text-text-secondary">{r.where}</td>
                  <td className="py-2 text-text-muted">{r.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      <OperatorControls />
    </div>
  );
}
