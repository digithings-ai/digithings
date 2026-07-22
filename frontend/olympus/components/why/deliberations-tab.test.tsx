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

  it('keeps PM/rebalance memos out of the ticker-level archive', () => {
    const docs = [
      { path: 'pm-rebalance' },
      { path: 'pm-allocation-memo/2026-07-20.json' },
      { path: 'rebalance-decision.json' },
      { path: 'deliberation/NVDA' },
      { path: 'deliberation-transcript/2026-07-20/NVDA.json' },
      { path: 'asset-recommendations/2026-07-20/NVDA.json' },
    ];
    expect(docs.filter(isPmMemoHistoryDoc).map((doc) => doc.path)).toEqual([
      'pm-rebalance',
      'pm-allocation-memo/2026-07-20.json',
      'rebalance-decision.json',
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
