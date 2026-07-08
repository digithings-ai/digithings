'use client';

import { ArrowLeft } from 'lucide-react';
import type { FxBriefRow } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';

export default function BriefsIndex({ briefs, onBack }: { briefs: FxBriefRow[]; onBack: () => void }) {
  const { openBrief } = useTwelveX();
  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-center gap-3">
        <button type="button" className="flex items-center gap-1 text-xs text-accent hover:underline" onClick={onBack}>
          <ArrowLeft size={14} /> Today
        </button>
        <h2 className="text-base font-semibold text-ink">Today&rsquo;s briefs</h2>
        <span className="ml-auto font-mono text-[10px] text-ink-mute">{briefs.length}</span>
      </header>
      {briefs.length === 0 ? (
        <div className="glass-card p-10 text-center text-sm text-ink-mute">No research briefs for today yet.</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {briefs.map((b, i) => (
            <button
              key={`${b.source_file}-${i}`}
              type="button"
              className="glass-card p-4 text-left transition-colors hover:border-accent/50"
              onClick={() => openBrief(b.source_file, b.run_date)}
            >
              <div className="flex items-center gap-2 text-[11px] text-ink-mute">
                <span className="font-semibold text-ink-soft">{b.broker_name ?? 'Unknown desk'}</span>
                {b.trader_relevance ? <span className="uppercase">· {b.trader_relevance}</span> : null}
              </div>
              <p className="mt-1 text-sm font-medium text-ink">{b.document_title ?? b.source_file}</p>
              {b.central_thesis ? <p className="mt-1 line-clamp-3 text-xs text-ink-soft">{b.central_thesis}</p> : null}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
