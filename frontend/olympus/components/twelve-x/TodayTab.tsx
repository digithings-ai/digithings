'use client';

import { Sparkles, FileText, Users } from 'lucide-react';
import { SafeMarkdown } from '@/components/SafeMarkdown';
import type { FxConfluenceSnapshotRow } from '@/lib/twelve-x/types';

interface DigestData {
  run_date: string;
  headline: string;
  summary: string;
  key_themes: string[];
  doc_count: number;
  broker_count: number;
}

/** Map a confluence/consensus direction string to a .fin-* text color class. */
function directionColorClass(direction: string): string {
  const d = direction.trim().toLowerCase();
  if (d === 'bullish' || d === 'long' || d === 'buy') return 'text-fin-green';
  if (d === 'bearish' || d === 'short' || d === 'sell') return 'text-fin-red';
  if (d === 'watch') return 'text-fin-amber';
  return 'text-text-secondary';
}

function directionLabel(direction: string): string {
  const d = direction.trim();
  if (!d) return '—';
  return d.charAt(0).toUpperCase() + d.slice(1).toLowerCase();
}

function ConfluenceCard({ idea }: { idea: FxConfluenceSnapshotRow }) {
  const colorClass = directionColorClass(idea.direction);
  return (
    <div className="glass-card p-4 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.06] text-text-muted border border-border-subtle shrink-0">
            #{idea.rank}
          </span>
          <span className="font-mono text-sm font-semibold text-text-primary truncate">{idea.currency}</span>
        </div>
        <span className={`text-xs font-semibold shrink-0 ${colorClass}`}>{directionLabel(idea.direction)}</span>
      </div>
      <p className="text-sm text-text-primary leading-snug">{idea.title}</p>
      <div className="mt-auto flex items-center justify-between pt-1">
        <span className="text-[11px] text-text-muted uppercase tracking-wider">Score</span>
        <span className={`qn-metric tabular-nums ${colorClass}`}>
          {Number.isFinite(idea.score) ? idea.score.toFixed(2) : '—'}
        </span>
      </div>
    </div>
  );
}

export default function TodayTab({
  digest,
  confluence,
}: {
  digest: DigestData | null;
  confluence: FxConfluenceSnapshotRow[];
}) {
  if (!digest) {
    return (
      <div className="glass-card p-10 text-center text-text-muted text-sm">
        No FX daily digest is available yet.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Greeting / digest header */}
      <div className="glass-card p-5 md:p-6 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Sparkles size={18} className="text-fin-blue shrink-0" />
          <h2 className="text-lg md:text-xl font-semibold text-text-primary">{digest.headline}</h2>
          <span className="text-[10px] font-mono text-text-muted ml-auto">{digest.run_date}</span>
        </div>

        {digest.summary ? (
          <SafeMarkdown className="prose prose-invert max-w-none text-sm text-text-secondary">
            {digest.summary}
          </SafeMarkdown>
        ) : null}

        {digest.key_themes.length > 0 ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {digest.key_themes.map((theme, i) => (
              <span
                key={`${theme}-${i}`}
                className="text-[11px] font-medium px-2.5 py-1 rounded-full border border-fin-blue/30 bg-fin-blue/10 text-fin-blue"
              >
                {theme}
              </span>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-text-muted pt-1 border-t border-border-subtle/60 mt-1">
          <span className="flex items-center gap-1.5">
            <FileText size={13} aria-hidden />
            <span className="qn-metric text-text-secondary tabular-nums">{digest.doc_count}</span>
            documents
          </span>
          <span className="flex items-center gap-1.5">
            <Users size={13} aria-hidden />
            <span className="qn-metric text-text-secondary tabular-nums">{digest.broker_count}</span>
            brokers
          </span>
        </div>
      </div>

      {/* Top trade ideas */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wider px-1">
          Top trade ideas
        </h3>
        {confluence.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {confluence.map((idea) => (
              <ConfluenceCard key={`${idea.run_date}-${idea.rank}`} idea={idea} />
            ))}
          </div>
        ) : (
          <div className="glass-card p-8 text-center text-text-muted text-sm">
            No confluence trade ideas for {digest.run_date}.
          </div>
        )}
      </div>
    </div>
  );
}
