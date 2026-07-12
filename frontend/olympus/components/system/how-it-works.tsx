'use client';

import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { NumberedStages, type NumberedStage } from '@digithings/web';
import { SectionCard } from '@/components/observability/shared';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { OperatorControls } from './operator-controls';

/** The run, one move at a time — same copy as the old prose paragraph,
 * recast on the shared numbered-stage spine (F4 #1450). `animated={false}`:
 * olympus has no MotionProvider (MotionLayer is deliberately CSS-only), so
 * the spine renders static — content reads with no JS and under reduced
 * motion by construction. */
const STAGES: NumberedStage[] = [
  {
    num: '01',
    tag: 'Atlas',
    title: 'Research the market',
    mech: 'Each run fans out across parallel phases — alternative data, institutional flows, macro, asset classes, and sectors — and synthesizes a daily read.',
  },
  {
    num: '02',
    tag: 'Hermes',
    title: 'Deliberate the book',
    mech: 'Hermes frames theses, screens candidates, runs per-ticker analysts and PM⇄analyst debates, and sizes risk.',
  },
  {
    num: '03',
    tag: 'Portfolio',
    title: 'Book the decisions',
    mech: 'The result is a booked portfolio with a signed decision behind every position.',
  },
];

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
        <NumberedStages stages={STAGES} animated={false} className="max-w-3xl pt-1" />
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
              <tr className="border-b border-hair text-left text-xs text-ink-mute">
                <th className="py-2 pr-4 font-medium">What</th>
                <th className="py-2 pr-4 font-medium">Where</th>
                <th className="py-2 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody>
              {PERSISTS.map((r) => (
                <tr key={r.what} className="border-b border-hair/50">
                  <td className="py-2 pr-4 text-ink">{r.what}</td>
                  <td className="py-2 pr-4 font-mono text-xs text-ink-soft">{r.where}</td>
                  <td className="py-2 text-ink-mute">{r.note}</td>
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
