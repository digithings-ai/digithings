'use client';

import type { ThesisStory } from '@/lib/thesis-story';
import { ThesisStoryCard } from '@/components/portfolio/theses/ThesisStoryCard';

/**
 * The Theses tab is a research-view library. Market narratives are ordered by
 * conviction and disclosed in place; portfolio-coverage diagnostics live with
 * data quality and pipeline monitoring rather than this reading surface.
 */
export function ThesisStorySpine({
  stories,
  asOf,
}: {
  stories: ThesisStory[];
  /** The spine's anchor date (the run the market theses come from). */
  asOf: string | null;
}) {
  return (
    <section data-region="thesis-ledger" className="min-w-0 border-y border-hair bg-surface">
      <div className="flex items-baseline justify-between gap-3 border-x border-b border-hair px-5 py-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-normal text-ink-mute">
            portfolio research
          </p>
          <h2 className="mt-1 font-display text-2xl text-ink">Research views</h2>
        </div>
        <p className="font-mono text-xs text-ink-mute">
          {asOf ? `As of ${asOf}` : 'Ordered by conviction'}
        </p>
      </div>
      <div className="border-x border-hair">
          {stories.length === 0 ? (
            <div className="px-6 py-8 text-sm text-ink-mute">
              No market views recorded yet.
            </div>
          ) : (
            <div>
              {stories.map((story, index) => (
                <ThesisStoryCard
                  key={story.thesis.id}
                  story={story}
                  defaultOpen={index === 0}
                  rank={index + 1}
                />
              ))}
            </div>
          )}
      </div>
    </section>
  );
}
