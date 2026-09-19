import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';
import {
  formatBoardDateShort,
  formatBoardRangeLabel,
} from './BoardDateRangeFilter';
import TradesTab from './TradesTab';

const ideas: FxTradeIdeaRow[] = [
  {
    run_date: '2026-07-24',
    rank: 1,
    pair: 'USD/JPY',
    direction: 'long',
    title: 'USD/JPY long',
    thesis: 'thesis',
    catalyst: 'FOMC',
    levels: [],
    citations: [],
    as_of: '2026-07-24T00:00:00Z',
    trade_levels: {
      entry_low: { value: '148.20', provenance: 'broker_quoted', source_ref: 'a.md' },
      entry_high: { value: '148.60', provenance: 'broker_quoted', source_ref: 'a.md' },
      stop: { value: '147.40', provenance: 'broker_quoted', source_ref: 'a.md' },
      targets: [{ value: '150.50', provenance: 'broker_quoted', source_ref: 'a.md' }],
    },
  },
  {
    run_date: '2026-07-20',
    rank: 1,
    pair: 'EUR/USD',
    direction: 'short',
    title: 'missing rates',
    thesis: 'thesis',
    catalyst: 'ECB',
    levels: [],
    citations: [],
    as_of: '2026-07-20T00:00:00Z',
  },
];

const ideaEval: FxIdeaEvalRow[] = [
  {
    run_date: '2026-07-24',
    rank: 1,
    horizon_days: 0,
    pair: 'USD/JPY',
    direction: 'long',
    status: 'resolved',
    entry_date: '2026-07-24',
    exit_date: '2026-07-31',
    entry_fix: 148,
    exit_fix: 149,
    ret: 0.012,
    hold_return: 0.012,
    sigma_entry: 0.005,
    hit: true,
    directional_win: true,
    significant_hit: true,
    n_sessions: 5,
    as_of: '2026-07-31T00:00:00Z',
  },
  {
    run_date: '2026-07-20',
    rank: 1,
    horizon_days: 0,
    pair: 'EUR/USD',
    direction: 'short',
    status: 'missing_rates',
    entry_date: null,
    exit_date: null,
    entry_fix: null,
    exit_fix: null,
    ret: null,
    hold_return: null,
    sigma_entry: null,
    hit: null,
    directional_win: null,
    significant_hit: null,
    n_sessions: 0,
    as_of: '2026-07-20T00:00:00Z',
  },
];

describe('TradesTab', () => {
  it('renders summary + history columns without secondary performance sections', () => {
    const html = renderToStaticMarkup(
      createElement(TradesTab, { ideas, ideaEval }),
    );

    expect(html).toContain('Trades');
    expect(html).toContain('data-testid="trades-summary"');
    expect(html).toContain('% right');
    expect(html).toContain('Avg return (rights)');
    expect(html).toContain('Avg return (wrongs)');
    expect(html).toContain('Generated');
    expect(html).toContain('Impact');
    expect(html).toContain('USD/JPY');
    expect(html).toContain('RIGHT');
    expect(html).toContain('>5<'); // Active days number, no ellipsis
    expect(html).not.toContain('History —');
    expect(html).not.toContain('Open ideas');
    expect(html).not.toContain('Performance — bias');
    expect(html).not.toContain('Performance — consensus');
    expect(html).not.toContain('NO DATA');
    expect(html).not.toContain('Levels');
    expect(html).not.toContain('…');
  });

  it('exposes Impact slider and board date range trigger (not binary chip / select)', () => {
    const html = renderToStaticMarkup(
      createElement(TradesTab, { ideas, ideaEval }),
    );

    // W4-A2: the hand-rolled <input type="range"> now renders the shared
    // @digithings/ui Slider. The kit part carries data-slot="slider" and its
    // own .ctl-slider-input mechanic (the same class the old native input
    // wore), so the existing pins still hold — strengthened, not weakened,
    // with the shared-part slot assertion.
    expect(html).toContain('data-testid="impact-min-slider"');
    expect(html).toContain('data-slot="slider"');
    expect(html).toContain('ctl-slider-input');
    expect(html).toContain('|Impact| ≥ 0%');
    expect(html).toContain('aria-label="Filter by board date range"');
    expect(html).toContain('All boards');
    expect(html).not.toContain('|Impact| ≥ 0.1%');
    expect(html).not.toContain('Filter by board date"');
    expect(html).not.toContain('<option value="all">All boards</option>');
  });

  it('uses DigiWeb DropdownMenu for pair filter (not native select)', () => {
    const html = renderToStaticMarkup(
      createElement(TradesTab, { ideas, ideaEval }),
    );

    expect(html).toContain('data-testid="pair-filter"');
    expect(html).toContain('aria-label="Filter by pair"');
    expect(html).toContain('All pairs');
    expect(html).not.toMatch(/<select[\s>]/);
    expect(html).not.toContain('<option value="all">All pairs</option>');
  });

  it('shows bookkeeper-dropped rows with their close reason', () => {
    const droppedIdea: FxTradeIdeaRow = {
      run_date: '2026-07-22',
      rank: 1,
      pair: 'GBP/USD',
      direction: 'short',
      title: 'GBP/USD short',
      thesis: 'thesis',
      catalyst: 'BoE',
      levels: [],
      citations: [],
      as_of: '2026-07-22T00:00:00Z',
    };
    const droppedEval: FxIdeaEvalRow = {
      run_date: '2026-07-22',
      rank: 1,
      horizon_days: 0,
      pair: 'GBP/USD',
      direction: 'short',
      status: 'dropped',
      entry_date: '2026-07-22',
      exit_date: '2026-07-30',
      entry_fix: 1.27,
      exit_fix: null,
      ret: null,
      hold_return: null,
      sigma_entry: null,
      hit: null,
      directional_win: null,
      significant_hit: null,
      n_sessions: 6,
      as_of: '2026-07-30T00:00:00Z',
      verdict_reason: 'thesis dead',
    };
    const html = renderToStaticMarkup(
      createElement(TradesTab, {
        ideas: [...ideas, droppedIdea],
        ideaEval: [...ideaEval, droppedEval],
      }),
    );

    expect(html).toContain('Status');
    expect(html).toContain('CLOSED');
    expect(html).toContain('title="thesis dead"');
    expect(html).toContain('Superseded');
    expect(html).toContain('Dropped');
  });

  it('renders a continuation marker for badged rows and nothing extra otherwise', () => {
    const plain = renderToStaticMarkup(
      createElement(TradesTab, { ideas, ideaEval }),
    );
    expect(plain).not.toContain('cont. since');

    const badgedEval = ideaEval.map((r) =>
      r.run_date === '2026-07-24' ? { ...r, continued_from: '2026-07-06', n_boards: 2 } : r,
    );
    const badged = renderToStaticMarkup(
      createElement(TradesTab, { ideas, ideaEval: badgedEval }),
    );
    expect(badged).toContain('· cont. since 2026-07-06');
  });

  it('shows a bookkeeper-dropped row with its close reason and the close tally', () => {
    const droppedIdea: FxTradeIdeaRow = {
      run_date: '2026-07-22',
      rank: 1,
      pair: 'GBP/USD',
      direction: 'short',
      title: 'GBP/USD short',
      thesis: 'thesis',
      catalyst: 'BoE',
      levels: [],
      citations: [],
      as_of: '2026-07-22T00:00:00Z',
    };
    const droppedEval: FxIdeaEvalRow = {
      run_date: '2026-07-22',
      rank: 1,
      horizon_days: 0,
      pair: 'GBP/USD',
      direction: 'short',
      status: 'dropped',
      entry_date: '2026-07-22',
      exit_date: '2026-07-27',
      entry_fix: 1.27,
      exit_fix: null,
      ret: null,
      hold_return: -0.003,
      sigma_entry: 0.004,
      hit: null,
      directional_win: null,
      significant_hit: null,
      n_sessions: 3,
      as_of: '2026-07-27T00:00:00Z',
      verdict_reason: 'thesis dead',
    };
    const html = renderToStaticMarkup(
      createElement(TradesTab, {
        ideas: [...ideas, droppedIdea],
        ideaEval: [...ideaEval, droppedEval],
      }),
    );

    expect(html).toContain('Status');
    expect(html).toContain('CLOSED');
    expect(html).toContain('title="thesis dead"');
    expect(html).toContain('Superseded');
    expect(html).toContain('Dropped');
    expect(html).toContain('-0.3%');
  });
});

describe('formatBoardRangeLabel', () => {
  it('labels all / single / range boards', () => {
    expect(formatBoardRangeLabel(null, null)).toBe('All boards');
    expect(formatBoardRangeLabel('2026-07-24', '2026-07-24')).toBe(
      formatBoardDateShort('2026-07-24'),
    );
    expect(formatBoardRangeLabel('2026-07-18', '2026-07-31')).toBe(
      `${formatBoardDateShort('2026-07-18')} – ${formatBoardDateShort('2026-07-31')}`,
    );
  });
});
