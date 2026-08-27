import { describe, expect, it } from 'vitest';
import {
  activeRebalanceActions,
  buildBriefHighlight,
  type BriefHighlightInput,
} from './brief-highlight';
import type { DashboardPositionEvent, RebalanceAction } from '@/lib/types';

const base: BriefHighlightInput = {
  headline: null,
  actions: [],
  rationaleByTicker: {},
  actionables: [],
  risks: [],
  contextBullets: [],
  latestEvent: null,
};

describe('activeRebalanceActions', () => {
  it('drops HOLD and zero-weight EXIT no-ops', () => {
    const actions: RebalanceAction[] = [
      { ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' },
      { ticker: 'QQQ', current_pct: 0, recommended_pct: 0, action: 'EXIT' },
      { ticker: 'NVDA', current_pct: 8, recommended_pct: 6, action: 'TRIM' },
    ];
    expect(activeRebalanceActions(actions).map((a) => a.ticker)).toEqual(['NVDA']);
  });
});

describe('buildBriefHighlight', () => {
  it('leads with a portfolio move and fills Research · Portfolio · Watch beats', () => {
    const latestEvent: DashboardPositionEvent = {
      date: '2026-08-05',
      ticker: 'XLF',
      event: 'ADD',
      weight_pct: 15.2,
      prev_weight_pct: 15.1,
      weight_change_pct: 0.1,
      price: null,
      thesis_id: null,
      reason: 'Maintain financial exposure while breadth confirms.',
    };
    const highlight = buildBriefHighlight({
      ...base,
      headline: 'Breadth improves while duration risk remains elevated.',
      actions: [
        {
          ticker: 'NVDA',
          current_pct: 8,
          recommended_pct: 6,
          action: 'TRIM',
          rationale: 'Valuation stretched into earnings.',
        },
        { ticker: 'XLF', current_pct: 15.1, recommended_pct: 16, action: 'ADD' },
      ],
      rationaleByTicker: {
        XLF: 'Maintain financial exposure while breadth confirms.',
      },
      actionables: [
        { label: 'Hold breadth above 65%', priority: 1, rationale: 'Confirms participation.' },
      ],
      risks: [{ label: 'Duration selloff', trigger: '10Y above 4.80%', horizonHours: 48 }],
      contextBullets: ['Gold strength conflicts with the risk-on breadth signal.'],
      latestEvent,
    });

    expect(highlight.attention).toBe('Trim NVDA — Valuation stretched into earnings.');
    expect(highlight.hasPipelineSignal).toBe(true);
    expect(highlight.beats).toHaveLength(3);
    expect(highlight.beats.map((b) => b.label)).toEqual(['Research', 'Portfolio', 'Watch']);
    expect(highlight.beats[0].text).toContain('Hold breadth above 65%');
    expect(highlight.beats[1].text).toContain('Trim NVDA');
    expect(highlight.beats[1].text).toContain('Also: Add XLF');
    expect(highlight.beats[2].text).toContain('Duration selloff');
    expect(highlight.beats.every((b) => b.available)).toBe(true);
  });

  it('falls back to research when the book is holding', () => {
    const highlight = buildBriefHighlight({
      ...base,
      headline: 'Mixed signals persist as tech leads equities and USD strengthens.',
      actions: [{ ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' }],
      actionables: [
        { label: 'Monitor DXY above 120.4', priority: 1, rationale: 'near YTD highs' },
      ],
      risks: [{ label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizonHours: 48 }],
    });

    expect(highlight.attention).toContain('Monitor DXY above 120.4');
    expect(highlight.beats[1].text).toBe('Holding the book — no allocation change recommended.');
    expect(highlight.beats[1].available).toBe(true);
    expect(highlight.beats[2].text).toContain('BOJ intervention');
  });

  it('uses honest empty copy when no pipeline artifacts exist', () => {
    const highlight = buildBriefHighlight(base);
    expect(highlight.attention).toBe('Nothing material was published for this run yet.');
    expect(highlight.hasPipelineSignal).toBe(false);
    expect(highlight.beats.every((b) => !b.available)).toBe(true);
    expect(highlight.beats[0].text).toContain('No research highlight');
    expect(highlight.beats[1].text).toContain('No portfolio decision');
    expect(highlight.beats[2].text).toContain('No watch item');
  });

  it('does not invent metrics or levels when only a headline exists', () => {
    const highlight = buildBriefHighlight({
      ...base,
      headline: 'Breadth improves while duration risk remains elevated.',
    });
    expect(highlight.attention).toBe('Breadth improves while duration risk remains elevated.');
    expect(highlight.beats[0].text).toBe('Breadth improves while duration risk remains elevated.');
    expect(highlight.attention).not.toMatch(/%|bps|confidence/i);
  });
});
