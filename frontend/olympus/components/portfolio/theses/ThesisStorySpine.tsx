'use client';

import type { ThesisStory, UnassignedGroup } from '@/lib/thesis-story';
import { normalizeThesisId } from '@/lib/thesis-id';
import { ThesisStoryCard } from '@/components/portfolio/theses/ThesisStoryCard';
import { UnassignedShelf } from '@/components/portfolio/theses/UnassignedShelf';

/**
 * The Theses tab body: market theses as a conviction-ordered story spine (each
 * expands to the vehicles that express it, each vehicle to its stock-level story),
 * with a trailing shelf for what the spine cannot place.
 */
export function ThesisStorySpine({
  stories,
  unassigned,
  weightByThesis,
  asOf,
}: {
  stories: ThesisStory[];
  unassigned: UnassignedGroup;
  /** Book weight each market thesis drives (primary-thesis attribution, no double-count). */
  weightByThesis: Map<string, number>;
  /** The spine's anchor date (the run the market theses come from). */
  asOf: string | null;
}) {
  return (
    <div className="space-y-12">
      <section className="space-y-4">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-display text-2xl text-ink">Market views</h2>
          <p className="text-xs text-ink-mute">
            Ordered by conviction
            {asOf ? <span className="font-mono"> · as of {asOf}</span> : null}
          </p>
        </div>
        {stories.length === 0 ? (
          <div className="glass-card p-6 text-sm text-ink-mute">No market views recorded yet.</div>
        ) : (
          <div className="space-y-4">
            {stories.map((story) => (
              <ThesisStoryCard
                key={story.thesis.id}
                story={story}
                bookWeightPct={weightByThesis.get(normalizeThesisId(story.thesis.id)) ?? 0}
              />
            ))}
          </div>
        )}
      </section>

      <UnassignedShelf
        heldUnmapped={unassigned.heldUnmapped}
        proposedUnheld={unassigned.proposedUnheld}
      />
    </div>
  );
}
