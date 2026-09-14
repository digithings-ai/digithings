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

describe('ThesisStorySpine — research library', () => {
  it('renders a simple dated research-view disclosure list', () => {
    const stories = [story({ thesis: thesis({ id: 'MT1', name: 'High conviction' }) })];

    const html = renderToStaticMarkup(
      createElement(ThesisStorySpine, {
        stories,
        asOf: '2026-07-17',
      })
    );

    expect(html).toContain('Market theses');
    expect(html).toContain('1 thesis · as of 2026-07-17');
    expect(html).toContain('High conviction');
  });

  it('does not render coverage metrics, an index, or unassigned shelves', () => {
    const html = renderToStaticMarkup(
      createElement(ThesisStorySpine, {
        stories: [story({ thesis: thesis({ id: 'MT1', name: 'A' }) })],
        asOf: '2026-07-17',
      })
    );

    expect(html).not.toContain('mapped exposure');
    expect(html).not.toContain('held unmapped');
    expect(html).not.toContain('proposed unheld');
    expect(html).not.toContain('Thesis index');
    expect(html).not.toContain('Unassigned');
    expect(html).not.toContain('drives');
  });
});

describe('ThesisStorySpine — disclosure default', () => {
  it('opens as a ranked register without expanding generated research prose', () => {
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
        asOf: '2026-07-17',
      })
    );

    const detailsMatches = html.match(/<details[^>]*>/g) || [];
    const openMatches = detailsMatches.filter((tag) => tag.includes('open'));

    expect(openMatches).toHaveLength(0);
    expect(html).toContain('3 theses · as of 2026-07-17');
    expect(html).toContain('High conviction');
    expect(html).toMatch(/border-y border-hair/);
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
  });
});
