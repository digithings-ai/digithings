import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DeliberationsStrip } from './deliberations-strip';
import type { PipelineTickerDoc } from '@/lib/types';

function render(transcripts: PipelineTickerDoc[]): string {
  return renderToStaticMarkup(createElement(DeliberationsStrip, { transcripts }));
}

const NVDA: PipelineTickerDoc = {
  document_key: 'deliberation/NVDA',
  ticker: 'NVDA',
  payload: {
    net_stance: 'bullish',
    conviction_delta: 1,
    bull_thesis: 'Datacenter capex supercycle intact.',
    bear_thesis: 'Multiple compression risk.',
  },
};

describe('DeliberationsStrip', () => {
  it('renders nothing when there are no debates', () => {
    expect(render([])).toBe('');
  });

  it('renders nothing when transcripts lack a debate payload (e.g. analyst-only)', () => {
    const noStance: PipelineTickerDoc = {
      document_key: 'analyst/SPY',
      ticker: 'SPY',
      payload: { conviction_score: 0.6 },
    };
    expect(render([noStance])).toBe('');
  });

  it('renders a card with ticker, stance, conviction delta, and theses', () => {
    const html = render([NVDA]);
    expect(html).toContain('NVDA');
    expect(html).toContain('bullish');
    expect(html).toContain('+1');
    expect(html).toContain('Datacenter capex');
    expect(html).toContain('Bull:');
    expect(html).toContain('Bear:');
  });
});
