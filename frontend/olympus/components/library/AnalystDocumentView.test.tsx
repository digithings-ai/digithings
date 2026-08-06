import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import AnalystDocumentView from './AnalystDocumentView';

const fullPayload = {
  ticker: 'qqq',
  conviction_score: -3,
  stance: 'sell',
  thesis: 'Tech is rolling over.',
  risks: 'A rate cut reverses the rotation.',
  sources: ['https://example.com/a'],
  fundamentals: 'Rich multiples.',
  technicals: 'Below the 50dma.',
  headwinds: ['Regulatory overhang'],
  tailwinds: ['AI capex'],
  bull_case: 'Earnings beat.',
  bear_case: 'Guidance cut.',
  price_targets: { base_case: 302 },
  expectations: 'Chop into earnings.',
  fingerprint_news_hash: 'abc123',
};

describe('AnalystDocumentView (#1562 PR4 convergence)', () => {
  it('no longer discards bull_case/bear_case/headwinds/tailwinds', () => {
    const html = renderToStaticMarkup(
      createElement(AnalystDocumentView, { payload: fullPayload, fallbackMarkdown: '' })
    );
    expect(html).toContain('Earnings beat.'); // bull_case
    expect(html).toContain('Guidance cut.'); // bear_case
    expect(html).toContain('Regulatory overhang'); // headwinds
    expect(html).toContain('AI capex'); // tailwinds
  });

  it('renders the shared fields identically to the dossier renderer', () => {
    const html = renderToStaticMarkup(
      createElement(AnalystDocumentView, { payload: fullPayload, fallbackMarkdown: '' })
    );
    expect(html).toContain('Tech is rolling over.'); // thesis
    expect(html).toContain('A rate cut reverses the rotation.'); // risks
    expect(html).toContain('Below the 50dma.'); // technicals
    expect(html).toContain('Chop into earnings.'); // expectations
    expect(html).toContain('Rich multiples.'); // fundamentals
    expect(html).toContain('https://example.com/a'); // sources
  });

  it('renders the ticker/stance/signed-conviction identity row', () => {
    const html = renderToStaticMarkup(
      createElement(AnalystDocumentView, { payload: fullPayload, fallbackMarkdown: '' })
    );
    expect(html).toContain('QQQ');
    expect(html).toContain('sell');
    expect(html).toContain('−3'); // SignedConvictionBadge, no clamp
  });

  it('falls back to markdown when payload is null', () => {
    const html = renderToStaticMarkup(
      createElement(AnalystDocumentView, { payload: null, fallbackMarkdown: '# Fallback prose' })
    );
    expect(html).toContain('Fallback prose');
  });

  it('falls back to markdown when the payload has no thesis or stance', () => {
    const html = renderToStaticMarkup(
      createElement(AnalystDocumentView, {
        payload: { ticker: 'AAA', sources: [] },
        fallbackMarkdown: '# Fallback prose',
      })
    );
    expect(html).toContain('Fallback prose');
  });
});
