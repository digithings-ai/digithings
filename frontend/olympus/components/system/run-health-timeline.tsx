'use client';

import { SectionCard } from '@/components/observability/shared';
import { groupRunEpisodes, type RunEpisode, type RunOutcome } from '@/lib/run-episodes';
import type { AtlasRunDiagnostics } from '@/lib/types';

// Status chrome, not P&L (F5) — ok/recovered ride the calm accent (matches the
// freshness banner dot); degraded/failed use --warn, never --up/--down.
const DOT: Record<RunOutcome, string> = {
  ok: 'bg-accent',
  recovered: 'bg-accent',
  degraded: 'bg-warn/60',
  failed: 'bg-warn',
};

function summary(ep: RunEpisode): string {
  const parts = [ep.runType ?? 'run'];
  if (ep.attempts > 1) parts.push(`${ep.attempts} attempts`);
  parts.push(ep.outcome);
  return parts.join(' · ');
}

export function RunHealthTimeline({ diagnostics }: { diagnostics: AtlasRunDiagnostics[] }) {
  const episodes = groupRunEpisodes(diagnostics);
  if (!episodes.length) return null;
  return (
    <SectionCard
      title="Run health"
      subtitle="Recent pipeline runs, grouped by day — retries collapse into one episode."
    >
      <ol className="flex flex-col gap-3">
        {episodes.map((ep) => (
          <li key={ep.key} className="flex items-start gap-3">
            <span
              className={`mt-1.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full ${DOT[ep.outcome]}`}
              aria-hidden
            />
            <div className="min-w-0">
              <p className="text-sm text-ink">
                <span className="font-medium">{ep.runDate ?? '—'}</span>{' '}
                <span className="text-ink-soft">— {summary(ep)}</span>
              </p>
              {ep.outcome !== 'ok' && ep.errorSummary ? (
                <p className="mt-0.5 truncate text-xs text-ink-mute" title={ep.errorSummary}>
                  {ep.errorSummary}
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </SectionCard>
  );
}
