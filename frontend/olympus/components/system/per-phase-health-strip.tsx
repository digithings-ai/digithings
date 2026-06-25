'use client';

import { SectionCard } from '@/components/observability/shared';
import { parsePhaseHealth } from '@/lib/run-phase-health';
import type { AtlasRunDiagnostics } from '@/lib/types';

export function PerPhaseHealthStrip({ latest }: { latest: AtlasRunDiagnostics }) {
  const phases = parsePhaseHealth(latest.breakdown);
  if (!phases.length) return null;
  return (
    <SectionCard
      title="Per-phase health"
      subtitle="Outputs produced per research phase — ok, carried forward, or failed — for the latest run."
    >
      <div className="flex flex-col gap-2">
        {phases.map((p) => {
          const total = p.ok + p.carried + p.failed || 1;
          return (
            <div key={p.phase} className="flex items-center gap-3 text-xs">
              <span className="w-16 shrink-0 text-text-muted">Phase {p.phase}</span>
              <span className="flex h-2 flex-1 overflow-hidden rounded-full bg-bg-secondary" aria-hidden>
                <span className="bg-fin-green" style={{ width: `${(p.ok / total) * 100}%` }} />
                <span className="bg-fin-amber" style={{ width: `${(p.carried / total) * 100}%` }} />
                <span className="bg-fin-red" style={{ width: `${(p.failed / total) * 100}%` }} />
              </span>
              <span className="w-20 shrink-0 text-right tabular-nums text-text-secondary">
                {p.ok}/{total}
                {p.carried > 0 ? <span className="text-fin-amber"> ·{p.carried}c</span> : null}
              </span>
            </div>
          );
        })}
      </div>
    </SectionCard>
  );
}
