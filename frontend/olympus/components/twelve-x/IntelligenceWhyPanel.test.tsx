import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import IntelligenceWhyPanel, { whyWaterfall } from './IntelligenceWhyPanel';
import type { IntelligenceWhyItem } from '@/lib/twelve-x/types';

const item = (over: Partial<IntelligenceWhyItem> = {}): IntelligenceWhyItem => ({
  currency: 'USD',
  rank: 1,
  direction: 'long',
  title: 'USD long into PCE',
  score: 0.8,
  components: {
    consensus_strength: 0.84,
    event_alignment: 0.8,
    recency: 1.0,
    breadth: 0.85,
    n_brokers: 17,
    days_to_catalyst: 0,
    timeframe: '1-3M',
  },
  consensus: {
    score: 1.1,
    confidence: 0.7,
    agreement: 0.66,
    tilt: 0.5,
    n_eff: 12,
    n_brokers: 17,
    n_views: 21,
    bullish_pct: 60,
    bearish_pct: 10,
    neutral_pct: 20,
    watch_pct: 10,
  },
  desks: [
    {
      broker: 'Atlas Macro',
      classification: 'active',
      relevance: 0.92,
      conviction: 'High',
      direction: 'bullish',
      reason: 'US rate resilience keeps the dollar bid.',
    },
    {
      broker: 'Old Mill FX',
      classification: 'superseded',
      relevance: 0.4,
      conviction: 'Low',
      direction: 'bearish',
      reason: 'Earlier Q2 dollar-top call has been overtaken.',
    },
  ],
  ...over,
});

function render(it: IntelligenceWhyItem): string {
  return renderToStaticMarkup(
    createElement(IntelligenceWhyPanel, { item: it, initialExpanded: true })
  );
}

describe('whyWaterfall (Tier-1 score legs)', () => {
  it('uses weights 0.50 / 0.30 / 0.20 with the event leg = alignment × recency', () => {
    const wf = whyWaterfall({
      consensus_strength: 0.84,
      event_alignment: 0.8,
      recency: 1.0,
      breadth: 0.85,
      n_brokers: 17,
      days_to_catalyst: 0,
      timeframe: '1-3M',
    });
    expect(wf.legs).toHaveLength(3);
    const [cons, event, breadth] = wf.legs;

    expect(cons.weight).toBe(0.5);
    expect(cons.input).toBeCloseTo(0.84);
    expect(cons.contribution).toBeCloseTo(0.5 * 0.84);

    expect(event.weight).toBe(0.3);
    // event leg input is alignment * recency
    expect(event.input).toBeCloseTo(0.8 * 1.0);
    expect(event.contribution).toBeCloseTo(0.3 * 0.8 * 1.0);

    expect(breadth.weight).toBe(0.2);
    expect(breadth.input).toBeCloseTo(0.85);
    expect(breadth.contribution).toBeCloseTo(0.2 * 0.85);
  });

  it('totals the three contributions', () => {
    const wf = whyWaterfall({
      consensus_strength: 0.84,
      event_alignment: 0.8,
      recency: 1.0,
      breadth: 0.85,
      n_brokers: 17,
      days_to_catalyst: 0,
      timeframe: '1-3M',
    });
    const expected = 0.5 * 0.84 + 0.3 * 0.8 * 1.0 + 0.2 * 0.85;
    expect(wf.total).toBeCloseTo(expected);
    expect(wf.total).toBeCloseTo(wf.legs.reduce((s, l) => s + l.contribution, 0));
  });
});

describe('IntelligenceWhyPanel', () => {
  it('renders the Tier-1 waterfall with the 0.50 / 0.30 / 0.20 weights visible', () => {
    const html = render(item());
    expect(html).toContain('Tier 1');
    expect(html).toContain('0.50');
    expect(html).toContain('0.30');
    expect(html).toContain('0.20');
    // the resulting confluence score is shown
    expect(html).toContain('Confluence');
  });

  it('renders Tier 2 with a ConsensusScoreBar and confidence/agreement/tilt figures', () => {
    const html = render(item());
    expect(html).toContain('Tier 2');
    // ConsensusScoreBar renders the dbar recipe
    expect(html).toContain('dbar-track');
    expect(html).toContain('Confidence');
    expect(html).toContain('Agreement');
    expect(html).toContain('Tilt');
    // split bar legend
    expect(html).toContain('Bull');
    expect(html).toContain('Bear');
    expect(html).toContain('Neutral');
    expect(html).toContain('Watch');
  });

  it('renders Tier 3 supporting desks with classification badges and verbatim reason', () => {
    const html = render(item());
    expect(html).toContain('Tier 3');
    expect(html).toContain('Atlas Macro');
    expect(html).toContain('active');
    expect(html).toContain('superseded');
    expect(html).toContain('US rate resilience keeps the dollar bid.');
    // relevance surfaced
    expect(html).toContain('relevance');
  });

  it('shows the synthesized one-liner with the exact "synthesized — would require generation" label', () => {
    const html = render(item());
    expect(html).toContain('synthesized — would require generation');
  });

  it('NEVER surfaces w_time or w_event', () => {
    const html = render(item());
    expect(html).not.toContain('w_time');
    expect(html).not.toContain('w_event');
  });

  it('guards a null consensus (no Tier-2 figures, no crash)', () => {
    const html = render(item({ consensus: null }));
    // still renders the other tiers
    expect(html).toContain('Tier 1');
    expect(html).toContain('Tier 3');
    // no consensus bar when there is no consensus row
    expect(html).not.toContain('dbar-track');
  });
});
