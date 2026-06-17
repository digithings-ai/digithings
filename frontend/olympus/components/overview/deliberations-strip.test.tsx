import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DeliberationsStrip } from './deliberations-strip';
import type { PipelineTickerDoc } from '@/lib/types';

function render(
  transcripts: PipelineTickerDoc[],
  riskDebate?: Record<string, unknown> | null,
): string {
  return renderToStaticMarkup(createElement(DeliberationsStrip, { transcripts, riskDebate }));
}

const RISK_DEBATE = {
  aggressive_case: 'Add beta into the breakout.',
  conservative_case: 'Keep the cash buffer.',
  key_tension: 'Momentum vs. participation.',
};

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

  it('renders the risk-debate card when a risk debate is present (#704)', () => {
    const html = render([], RISK_DEBATE);
    expect(html).not.toBe('');
    expect(html).toContain('Risk debate');
    expect(html).toContain('Key tension');
    expect(html).toContain('Momentum vs. participation.');
  });

  it('still renders nothing when both per-ticker debates and risk debate are absent', () => {
    expect(render([], null)).toBe('');
    expect(render([], { aggressive_case: 'only one field' })).toBe('');
  });

  it('renders both per-ticker debates and the risk debate together', () => {
    const html = render([NVDA], RISK_DEBATE);
    expect(html).toContain('NVDA');
    expect(html).toContain('Risk debate');
  });
});
