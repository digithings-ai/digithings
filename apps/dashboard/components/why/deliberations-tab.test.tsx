import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import {
  DeliberationsPanel,
  isPmMemoHistoryDoc,
  PmRebalancePanel,
  RiskDebatePanel,
  sortDocsByDateDesc,
} from './deliberations-tab';
import type { PipelineTickerDoc } from '@/lib/types';

describe('DeliberationsPanel', () => {
  it('renders a ticker debate with its net stance', () => {
    const docs: PipelineTickerDoc[] = [
      {
        document_key: 'deliberation/NVDA',
        ticker: 'NVDA',
        payload: {
          net_stance: 'bullish',
          bull_thesis: 'Datacenter capex compounding.',
          bear_thesis: 'Valuation rich into earnings.',
          conviction_delta: '2',
        },
      },
    ];
    const html = renderToStaticMarkup(createElement(DeliberationsPanel, { docs }));
    expect(html).toContain('NVDA');
    expect(html).toContain('bullish');
    expect(html).toContain('Datacenter capex');
    expect(html).toContain('data-testid="ticker-debate-ledger"');
    expect(html).not.toContain('glass-card');
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
  });

  it('renders nothing when no payload is a debate summary', () => {
    const docs: PipelineTickerDoc[] = [{ document_key: 'x', ticker: 'X', payload: { foo: 'bar' } }];
    expect(renderToStaticMarkup(createElement(DeliberationsPanel, { docs }))).toBe('');
  });

  // #4193 — coverage: the per-ticker debate ledger deep-links each ticker.
  it('links every debate ticker out to the Gloomberb terminal', () => {
    const docs: PipelineTickerDoc[] = [
      {
        document_key: 'deliberation/NVDA',
        ticker: 'NVDA',
        payload: {
          net_stance: 'bullish',
          bull_thesis: 'Datacenter capex compounding.',
          bear_thesis: 'Valuation rich into earnings.',
        },
      },
    ];
    const html = renderToStaticMarkup(createElement(DeliberationsPanel, { docs }));
    expect(html).toContain('data-testid="gloomberb-link-NVDA"');
    expect(html).toContain('href="https://term.gloom.sh/?ticker=NVDA"');
    const anchor = html.match(/<a[^>]*data-testid="gloomberb-link-NVDA"[^>]*>/)?.[0] ?? '';
    expect(anchor).toContain('target="_blank"');
    expect(anchor).toContain('rel="noopener noreferrer"');
    // The arrow idiom, not the external-link glyph (#4204).
    const block =
      html.match(/<a[^>]*data-testid="gloomberb-link-NVDA"[\s\S]*?<\/a>/)?.[0] ?? '';
    expect(block).toContain('lucide-arrow-up-right');
    expect(block).not.toContain('lucide-external-link');
  });

  // The third surface already guarded; pin the absent branch so the guard cannot
  // regress into an upstream default-symbol link.
  it('renders no Gloomberb link for a debate row with a blank ticker', () => {
    const docs: PipelineTickerDoc[] = [
      {
        document_key: 'deliberation/',
        ticker: '   ',
        payload: {
          net_stance: 'bullish',
          bull_thesis: 'Datacenter capex compounding.',
          bear_thesis: 'Valuation rich into earnings.',
        },
      },
    ];
    const html = renderToStaticMarkup(createElement(DeliberationsPanel, { docs }));
    expect(html).toContain('data-testid="ticker-debate-ledger"');
    expect(html).not.toContain('gloomberb-link');
    expect(html).not.toContain('term.gloom.sh');
  });
});

describe('sortDocsByDateDesc', () => {
  it('sorts the most recent (today) above older docs', () => {
    const sorted = sortDocsByDateDesc([
      { id: 'a', date: '2026-06-10' },
      { id: 'b', date: '2026-06-22' },
      { id: 'c', date: '2026-06-15' },
    ]);
    expect(sorted.map((d) => d.id)).toEqual(['b', 'c', 'a']);
  });

  it('keeps run-level portfolio docs and excludes only ticker-level artifacts', () => {
    const docs = [
      { path: 'pm-rebalance' },
      { path: 'pm-allocation-memo/2026-07-20.json' },
      { path: 'rebalance-decision.json' },
      { path: 'market-thesis-exploration/2026-07-20.json' },
      { path: 'thesis-vehicle-map/2026-07-20.json' },
      { path: 'opportunity-screen/2026-07-20.json' },
      { path: 'opportunity-screener.json' },
      { path: 'deliberation.md' },
      { path: 'deliberation.json' },
      { path: 'deliberation/NVDA' },
      { path: 'deliberation-transcript/2026-07-20/NVDA.json' },
      { path: 'deliberation-transcript-index/2026-07-20.json' },
      { path: 'asset-recommendations/2026-07-20/NVDA.json' },
    ];
    expect(docs.filter(isPmMemoHistoryDoc).map((doc) => doc.path)).toEqual([
      'pm-rebalance',
      'pm-allocation-memo/2026-07-20.json',
      'rebalance-decision.json',
      'market-thesis-exploration/2026-07-20.json',
      'thesis-vehicle-map/2026-07-20.json',
      'opportunity-screen/2026-07-20.json',
      'opportunity-screener.json',
      'deliberation.md',
      'deliberation.json',
    ]);
  });
});

describe('flat deliberation sections', () => {
  it('renders the rebalance memo as a flat action ledger', () => {
    const html = renderToStaticMarkup(createElement(PmRebalancePanel, {
      payload: {
        actions: [{ ticker: 'NVDA', action: 'trim', current_pct: 8, target_pct: 6, rationale: 'Risk budget.' }],
        notes: 'Reduce concentration.',
      },
    }));
    expect(html).toContain('data-testid="rebalance-ledger"');
    expect(html).not.toContain('glass-card');
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
  });

  it('renders the risk debate without money-colored stance labels', () => {
    const html = renderToStaticMarkup(createElement(RiskDebatePanel, {
      payload: {
        aggressive_case: 'Add cyclical exposure.',
        conservative_case: 'Keep dry powder.',
        key_tension: 'Growth versus valuation.',
      },
    }));
    expect(html).toContain('data-testid="risk-debate-ledger"');
    expect(html).not.toContain('glass-card');
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
  });
});
