import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import LibraryDocumentBody from './LibraryDocumentBody';
import PmDirectionDocumentView from './PmDirectionDocumentView';

const AUG31_MEMO = {
  schema_version: '1.0',
  date: '2026-08-31',
  memo: 'Stay long gold as ballast; keep duration flat.',
  roster: [
    {
      ticker: 'TLT',
      direction: 'flat',
      conviction_rank: 3,
      narrative: 'Duration still expensive versus the bias row.',
      confidence: 0.4,
      forecast_reference: {
        ticker: 'TLT',
        effective_forecast_id: null,
        base_forecast_id: null,
        degradation_reason: 'forecast_unavailable',
      },
    },
    {
      ticker: 'GLD',
      direction: 'long',
      conviction_rank: 1,
      narrative: 'Real-yield relief still supports the metal.',
      confidence: 0.9,
      forecast_reference: {
        ticker: 'GLD',
        effective_forecast_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        degradation_reason: null,
      },
    },
    {
      ticker: 'QQQ',
      direction: 'long',
      conviction_rank: 2,
      narrative: 'Hold the core; do not add into the stretch.',
      confidence: 0.55,
    },
  ],
};

function render(props: {
  payload?: Record<string, unknown> | null;
  fallbackMarkdown?: string;
  priorRoster?: Array<{ ticker: string; direction: string }>;
  rebalance?: Record<string, unknown> | null;
}) {
  return renderToStaticMarkup(
    createElement(PmDirectionDocumentView, {
      payload: props.payload === undefined ? AUG31_MEMO : props.payload,
      fallbackMarkdown: props.fallbackMarkdown ?? '# Fallback',
      priorRoster: props.priorRoster,
      rebalance: props.rebalance,
    }),
  );
}

describe('PmDirectionDocumentView', () => {
  it('renders memo, narratives, rank, and confidence percent', () => {
    const html = render({});
    expect(html).toContain('data-testid="pm-direction-document-view"');
    expect(html).toContain('Stay long gold as ballast');
    expect(html).toContain('GLD');
    expect(html).toContain('Real-yield relief still supports the metal.');
    expect(html).toContain('90%');
    expect(html).toContain('55%');
  });

  it('never shows forecast_reference UUIDs or degradation_reason', () => {
    const html = render({});
    expect(html).not.toContain('forecast_reference');
    expect(html).not.toContain('forecast_unavailable');
    expect(html).not.toContain('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa');
    expect(html).not.toContain('degradation');
  });

  it('lists longs before flats, each group ordered by rank', () => {
    const html = render({});
    const gld = html.indexOf('GLD');
    const qqq = html.indexOf('QQQ');
    const tlt = html.indexOf('TLT');
    expect(gld).toBeGreaterThan(-1);
    expect(qqq).toBeGreaterThan(gld);
    expect(tlt).toBeGreaterThan(qqq);
  });

  it('derives buy/hold/sell from prior weights vs H8 targets', () => {
    const html = render({
      rebalance: {
        actions: [
          { ticker: 'GLD', action: 'add', current_pct: 4, target_pct: 10 },
          { ticker: 'QQQ', action: 'hold', current_pct: 12, target_pct: 12 },
          { ticker: 'TLT', action: 'exit', current_pct: 3, target_pct: 0 },
        ],
      },
    });
    expect(html).toContain('Buy');
    expect(html).toContain('Hold');
    expect(html).toContain('Sell');
  });

  it('falls back to long/flat when no prior or rebalance is at hand', () => {
    const html = render({});
    expect(html).toContain('Long');
    expect(html).toContain('Flat');
    expect(html).not.toContain('Buy');
    expect(html).not.toContain('Sell');
  });

  it('falls back to markdown when the payload has no roster or memo', () => {
    const html = render({ payload: null, fallbackMarkdown: '# Direction fallback' });
    expect(html).toContain('Direction fallback');
    expect(html).not.toContain('data-testid="pm-direction-document-view"');
  });

  it('LibraryDocumentBody routes pm_direction to the dedicated view', () => {
    const html = renderToStaticMarkup(
      createElement(LibraryDocumentBody, {
        view: 'pm_direction',
        markdown: '',
        payload: AUG31_MEMO,
        documentKey: 'pm-direction-memo',
        docDate: '2026-08-31',
      }),
    );
    expect(html).toContain('data-testid="pm-direction-document-view"');
    expect(html).not.toContain('forecast_unavailable');
  });
});
