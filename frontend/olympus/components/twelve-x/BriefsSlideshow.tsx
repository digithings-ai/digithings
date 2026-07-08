'use client';

import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { FxBriefRow } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';

export default function BriefsSlideshow({
  briefs,
  onSeeMore,
}: {
  briefs: FxBriefRow[];
  onSeeMore: () => void;
}) {
  const { openBrief } = useTwelveX();
  const [i, setI] = useState(0);

  if (briefs.length === 0) {
    return (
      <section className="glass-card p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-soft">Today&rsquo;s briefs</h2>
        <p className="mt-2 text-sm text-ink-mute">No research briefs for today yet.</p>
      </section>
    );
  }

  const idx = Math.min(i, briefs.length - 1);
  const b = briefs[idx];
  const go = (d: number) => setI((idx + d + briefs.length) % briefs.length);

  return (
    <section className="glass-card flex flex-col gap-3 p-5">
      <header className="flex items-baseline gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-soft">Today&rsquo;s briefs</h2>
        <span className="font-mono text-[10px] text-ink-mute">{idx + 1}/{briefs.length}</span>
        <button type="button" className="ml-auto text-[11px] text-accent hover:underline" onClick={onSeeMore}>
          see all →
        </button>
      </header>

      <div className="flex items-center gap-2">
        <button type="button" aria-label="Previous brief" className="rounded-md border border-hair p-1 text-ink-mute hover:text-accent" onClick={() => go(-1)}>
          <ChevronLeft size={16} />
        </button>
        <button
          type="button"
          className="min-w-0 flex-1 rounded-lg border border-hair p-3 text-left transition-colors hover:border-accent/50"
          onClick={() => openBrief(b.source_file, b.run_date)}
        >
          <div className="flex items-center gap-2 text-[11px] text-ink-mute">
            <span className="font-semibold text-ink-soft">{b.broker_name ?? 'Unknown desk'}</span>
            {b.trader_relevance ? <span className="uppercase">· {b.trader_relevance}</span> : null}
          </div>
          <p className="mt-1 truncate text-sm font-medium text-ink">{b.document_title ?? b.source_file}</p>
          {b.central_thesis ? <p className="mt-1 line-clamp-2 text-xs text-ink-soft">{b.central_thesis}</p> : null}
        </button>
        <button type="button" aria-label="Next brief" className="rounded-md border border-hair p-1 text-ink-mute hover:text-accent" onClick={() => go(1)}>
          <ChevronRight size={16} />
        </button>
      </div>

      <div className="flex justify-center gap-1">
        {briefs.map((bb, n) => (
          <button
            key={`${bb.source_file}-${bb.run_date}-${n}`}
            type="button"
            aria-label={`Go to brief ${n + 1}`}
            className={`h-1.5 w-1.5 rounded-full ${n === idx ? 'bg-accent' : 'bg-ink/20'}`}
            onClick={() => setI(n)}
          />
        ))}
      </div>
    </section>
  );
}
