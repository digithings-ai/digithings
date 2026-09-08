import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import BiasRowDocumentView from './BiasRowDocumentView';
import InputsDocumentView from './InputsDocumentView';

describe('InputsDocumentView', () => {
  it('renders watchlist, freshness, and prior-context dates', () => {
    const html = renderToStaticMarkup(
      createElement(InputsDocumentView, {
        payload: {
          doc_type: 'inputs',
          date: '2026-08-31',
          watchlist: ['SPY', 'QQQ'],
          profile: {
            profile_config_version_id: '11111111-1111-1111-1111-111111111111',
            preferences_digest: 'abc123',
          },
          market_data: {
            price_technicals_latest: '2026-08-29',
            macro_series_latest: '2026-08-28',
            stale_price: false,
            stale_macro: true,
            price_basket_gap: ['FXI'],
          },
          prior_context: {
            last_snapshot_date: '2026-08-28',
            active_theses_count: 2,
          },
          attention_plan_key: 'attention-plan',
        },
        fallbackMarkdown: '',
      }),
    );
    expect(html).toContain('SPY');
    expect(html).toContain('QQQ');
    expect(html).toContain('2026-08-29');
    expect(html).toContain('attention-plan');
    expect(html).not.toContain('{');
  });

  it('falls back to markdown when payload is empty', () => {
    const html = renderToStaticMarkup(
      createElement(InputsDocumentView, { payload: null, fallbackMarkdown: '# Inputs fallback' }),
    );
    expect(html).toContain('Inputs fallback');
  });
});

describe('BiasRowDocumentView', () => {
  it('renders a compact bias table and notes', () => {
    const html = renderToStaticMarkup(
      createElement(BiasRowDocumentView, {
        payload: {
          doc_type: 'bias_row',
          date: '2026-08-31',
          macro_regime: 'Slowing',
          equity_bias: 'bullish',
          crypto_bias: 'neutral',
          vix_level: 15.2,
          notes: 'VIX still compressed.',
        },
        fallbackMarkdown: '',
      }),
    );
    expect(html).toContain('Slowing');
    expect(html).toContain('bullish');
    expect(html).toContain('VIX still compressed.');
  });
});
