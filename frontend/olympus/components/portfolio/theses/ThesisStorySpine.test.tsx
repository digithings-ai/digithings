import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { ThesisStorySpine } from './ThesisStorySpine';
import type { ThesisStory } from '@/lib/thesis-story';
import type { Thesis } from '@/lib/types';

const thesis = (over: Partial<Thesis> = {}): Thesis => ({
  id: 'MT1',
  name: 'Market view',
  vehicle: null,
  invalidation: null,
  status: 'ACTIVE',
  notes: null,
  confidence: null,
  horizon: null,
  thesis_kind: 'market',
  validation_criteria: [],
  invalidation_criteria: [],
  linked_market_thesis_id: null,
  ...over,
});

const story = (over: Partial<ThesisStory>): ThesisStory => ({
  thesis: thesis(),
  vehicles: [],
  asOf: '2026-07-17',
  ...over,
});

describe('ThesisStorySpine — one-open disclosure default', () => {
  it('opens only the first/highest-conviction thesis by default, not all', () => {
    const stories = [
      story({
        thesis: thesis({
          id: 'MT1',
          name: 'High conviction',
          confidence: 0.9,
          validation_criteria: ['Demand accelerates'],
          invalidation_criteria: ['Demand contracts'],
        }),
      }),
      story({ thesis: thesis({ id: 'MT2', name: 'Medium conviction', confidence: 0.6 }) }),
      story({ thesis: thesis({ id: 'MT3', name: 'Low conviction', confidence: 0.3 }) }),
    ];

    const html = renderToStaticMarkup(
      createElement(ThesisStorySpine, {
        stories,
        unassigned: { heldUnmapped: [], proposedUnheld: [] },
        weightByThesis: new Map(),
        asOf: '2026-07-17',
      })
    );

    // Count how many <details> elements have the "open" attribute
    // The first story should be open, the rest closed
    const detailsMatches = html.match(/<details[^>]*>/g) || [];
    const openMatches = detailsMatches.filter((tag) => tag.includes('open'));

    expect(openMatches.length).toBe(1); // Only one thesis should be open
    expect(html).toContain('High conviction'); // First thesis is rendered
    expect(html.match(/glass-card/g)).toHaveLength(stories.length);
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
  });
});
