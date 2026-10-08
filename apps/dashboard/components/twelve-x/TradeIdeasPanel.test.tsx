import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import type { FxTradeIdeaRow, FxTradeLevels } from '@/lib/twelve-x/types';
import TradeIdeasPanel, { IdeaDetail, ideaDetailBlocksClass } from './TradeIdeasPanel';
import { TwelveXProvider } from './context';

const IDEAS: FxTradeIdeaRow[] = [
  {
    run_date: '2026-07-22',
    rank: 1,
    pair: 'USD/JPY',
    direction: 'short',
    title: 'JPY SHORT — via USD/JPY',
    thesis: 'BoJ normalization path repricing.',
    catalyst: 'BoJ minutes Thursday',
    levels: [],
    citations: [{ broker: 'Desk Alpha', source_file: 'alpha/usdjpy.md' }],
    as_of: '2026-07-22T10:00:00Z',
  },
  {
    run_date: '2026-07-22',
    rank: 2,
    pair: 'EUR/USD',
    direction: 'long',
    title: 'EUR grind higher',
    thesis: 'Rate differential compression.',
    catalyst: 'ECB speakers',
    levels: [],
    citations: [{ source_file: 'beta/eurusd-note.md' }],
    as_of: '2026-07-22T10:00:00Z',
  },
];

const LEVELS_IDEA: FxTradeIdeaRow = {
  ...IDEAS[0],
  trade_levels: {
    entry_low: {
      value: '1.15',
      provenance: 'computed',
      source_ref: 'computed:vol20@2026-07-31|k=1.5|rr=1.5',
    },
    entry_high: {
      value: '1.16',
      provenance: 'computed',
      source_ref: 'computed:vol20@2026-07-31|k=1.5|rr=1.5',
    },
    stop: {
      value: '1.14',
      provenance: 'computed',
      source_ref: 'computed:vol20@2026-07-31|k=1.5|rr=1.5',
    },
    targets: [{ value: '1.18', provenance: 'broker_quoted', source_ref: 'ING.pdf' }],
    risk_reward: 1.5,
    status: 'partial',
  },
  evidence: [
    {
      source_slug: 'dmx-overview',
      instrument: 'USD/JPY',
      as_of: '2026-08-01T00:00:00Z',
      statement: 'Retail 78% long USD/JPY',
      stance: 'contradicts',
      snapshot_id: '00000000-0000-0000-0000-000000000002',
    },
  ],
};

/**
 * DIG-260: the real production shape — a broker target survived the guard, the
 * entry band and stop did not. `partial` means never published as a bracket.
 */
const TARGET_ONLY_IDEA: FxTradeIdeaRow = {
  ...IDEAS[0],
  trade_levels: {
    targets: [{ value: '1.18', provenance: 'broker_quoted', source_ref: 'ING.pdf' }],
    risk_reward: null,
    status: 'partial',
  },
};

/** Shape-complete but still labelled non-complete: the guard dropped nothing. */
const POPULATED_BUT_PARTIAL_IDEA: FxTradeIdeaRow = {
  ...IDEAS[0],
  trade_levels: {
    ...(LEVELS_IDEA.trade_levels as FxTradeLevels),
    status: 'partial',
  },
};

const PUBLISHED_IDEA: FxTradeIdeaRow = {
  ...IDEAS[0],
  trade_levels: {
    ...(LEVELS_IDEA.trade_levels as FxTradeLevels),
    status: 'complete',
  },
};

const PENDING_COPY =
  'Not published — entry, stop and target appear together, or not at all.';

function renderDetail(idea: FxTradeIdeaRow): string {
  return renderToStaticMarkup(createElement(IdeaDetail, { idea }));
}

/** The pending element's class list, so a styling pin does not go substring-blind. */
function pendingClass(html: string): string | undefined {
  const tag = html.match(/<p[^>]*data-testid="trade-levels-pending"[^>]*>/)?.[0];
  return tag?.match(/class="([^"]*)"/)?.[1];
}

function render(
  ideas: FxTradeIdeaRow[],
  ideaHistory?: Pick<FxTradeIdeaRow, 'run_date' | 'pair' | 'direction' | 'as_of'>[],
  openIdea: ReturnType<typeof vi.fn> = vi.fn(),
): string {
  return renderToStaticMarkup(
    createElement(
      TwelveXProvider,
      {
        value: {
          runDate: '2026-07-22',
          crossLink: vi.fn(),
          openBrief: vi.fn(),
          openIdea,
          watchlist: { tickers: [], has: () => false, toggle: vi.fn() } as never,
        },
        children: createElement(TradeIdeasPanel, {
          ideas,
          ideaHistory,
        }),
      } as never,
    ),
  );
}

describe('TradeIdeasPanel', () => {
  it('renders the focal #1 idea and compact rows for the rest', () => {
    const html = render(IDEAS);
    expect(html).toContain('USD/JPY');
    expect(html).toContain('EUR/USD');
    expect(html).toContain('#1');
    expect(html).toContain('#2');
  });

  it('cards open the idea sidebar instead of expanding in place (#1664)', () => {
    const html = render(IDEAS);
    // Cards are plain buttons that open the sidebar; no inline disclosure state.
    expect(html).not.toContain('aria-expanded="false"');
    // Detail (contributing desks, levels) only lives in the sidebar, never inline.
    expect(html).not.toContain('Contributing desks');
    expect(html).not.toContain('Levels');
  });

  it('keeps direction off the P&L tokens', () => {
    const html = render(IDEAS);
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
  });

  it('does not show levels/evidence while collapsed', () => {
    const html = render([LEVELS_IDEA, IDEAS[1]]);
    expect(html).not.toContain('ING target');
    expect(html).not.toContain('Retail 78% long');
  });

  it('omits Levels header when trade_levels are empty', () => {
    const html = render(IDEAS);
    expect(html).not.toContain('Levels');
    expect(html).not.toContain('Market evidence');
  });

  it('stamps continuity in the card header from idea history', () => {
    const history = [
      { run_date: '2026-07-20', pair: 'USD/JPY', direction: 'short', as_of: '2026-07-20T09:00:00Z' },
      { run_date: '2026-07-21', pair: 'USD/JPY', direction: 'short', as_of: '2026-07-21T09:00:00Z' },
      { run_date: '2026-07-22', pair: 'USD/JPY', direction: 'short', as_of: '2026-07-22T10:00:00Z' },
      { run_date: '2026-07-22', pair: 'EUR/USD', direction: 'long', as_of: '2026-07-22T10:00:00Z' },
    ];
    const html = render(IDEAS, history);
    expect(html).toContain('First suggested 20 Jul');
    expect(html).toContain('Updated 22 Jul 10:00 UTC');
    expect(html).toContain('Suggested 22 Jul');
    // Two-line wrap-friendly stamp (no shrink-0 forcing overflow past the card).
    expect(html).toContain('min-w-0 max-w-[min(100%,14rem)]');
    expect(html).toContain('block break-words');
    expect(html).not.toMatch(/ml-auto shrink-0 text-right font-mono/);
  });

  it('merges current ideas into history when board date is missing from lookback', () => {
    // History ends before the displayed board — without merge, continuity would be empty.
    const history = [
      { run_date: '2026-07-20', pair: 'USD/JPY', direction: 'short', as_of: '2026-07-20T09:00:00Z' },
      { run_date: '2026-07-21', pair: 'USD/JPY', direction: 'short', as_of: '2026-07-21T09:00:00Z' },
    ];
    const html = render(IDEAS, history);
    expect(html).toContain('First suggested 20 Jul');
    expect(html).toContain('Updated 22 Jul 10:00 UTC');
    expect(html).toContain('Suggested 22 Jul');
  });

  it('uses single-column layout when only evidence or only levels are present', () => {
    expect(ideaDetailBlocksClass(true, true)).toContain('sm:grid-cols-2');
    expect(ideaDetailBlocksClass(false, true)).not.toContain('sm:grid-cols-2');
    expect(ideaDetailBlocksClass(true, false)).not.toContain('sm:grid-cols-2');

    const evidenceOnly: FxTradeIdeaRow = {
      ...IDEAS[0],
      trade_levels: undefined,
      evidence: LEVELS_IDEA.evidence,
    };
    const html = renderToStaticMarkup(createElement(IdeaDetail, { idea: evidenceOnly }));
    expect(html).toContain('Market evidence');
    expect(html).not.toContain('Levels');
    expect(html).not.toContain('sm:grid-cols-2');
  });

  it('labels evidence rows with source and instrument and folds boilerplate behind a detail toggle', () => {
    const smartBiasIdea: FxTradeIdeaRow = {
      ...IDEAS[0],
      trade_levels: undefined,
      evidence: [
        {
          source_slug: 'smart-bias-tracker',
          instrument: 'EUR',
          as_of: '2026-09-06T00:00:00Z',
          statement:
            'PMT Smart Bias weak bearish for EUR (week of 2026-09-06); factors: Trend_Sentiment=range; banks: 3/11 bullish',
          stance: 'supports',
          snapshot_id: '00000000-0000-0000-0000-000000000003',
        },
      ],
    };
    const html = renderToStaticMarkup(createElement(IdeaDetail, { idea: smartBiasIdea }));
    expect(html).toContain('Smart Bias · EUR');
    expect(html).toContain('PMT Smart Bias weak bearish for EUR (week of 2026-09-06)');
    expect(html).not.toContain('factors:');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('detail');
  });
});

/**
 * DIG-260: the pending trade-levels state, per the Designer's spec on DIG-2273 §1
 * and the DIG-2352 refinement — one sentence, hairline-framed only when it fills
 * one cell of the two-cell grid beside evidence, bare prose otherwise. No
 * skeleton, no shimmer, no reserved height, no new tokens. A non-published
 * bracket shows nothing actionable: no ladder row, no R:R, no level-vs-fix chart.
 */
describe('IdeaDetail — pending trade levels', () => {
  it('frames the pending slot when a pending bracket sits beside evidence', () => {
    const html = renderDetail({ ...TARGET_ONLY_IDEA, evidence: LEVELS_IDEA.evidence });
    expect(html).toContain('data-testid="trade-levels-pending"');
    expect(html).toContain(PENDING_COPY);
    // The frame marks one cell of a two-cell grid, so it is what says
    // "intentionally empty" next to the published evidence column.
    expect(html).toContain('rounded-none border border-hair bg-surface/40');
    // The copy must not echo the 'Levels' header directly above it.
    expect(html).not.toContain('Levels pending');
  });

  it('drops the frame when the pending bracket is the only column', () => {
    const html = renderDetail(TARGET_ONLY_IDEA);
    expect(html).toContain('data-testid="trade-levels-pending"');
    expect(html).toContain(PENDING_COPY);
    // No second cell, so no slot to mark: with no grid position to reference the
    // box would read as a callout, which is the opposite of the truth here.
    expect(html).not.toContain('border border-hair');
    expect(html).not.toContain('bg-surface/40');
    // Pinned exactly: bare prose, matching the `Catalyst:` caption it now sits under.
    expect(pendingClass(html)).toBe('text-[11px] leading-relaxed text-ink-mute');
  });

  it('replaces a populated-but-partial bracket with the same block, no ladder', () => {
    const html = renderDetail(POPULATED_BUT_PARTIAL_IDEA);
    expect(html).toContain('data-testid="trade-levels-pending"');
    expect(html).toContain(PENDING_COPY);
    // The shape was complete enough to build three rungs — none may reach the screen.
    expect(html).not.toContain('>Entry<');
    expect(html).not.toContain('>Stop<');
    expect(html).not.toContain('>Target<');
    expect(html).not.toContain('R:R');
  });

  it('renders no level-vs-fix section for a bracket that was not published', () => {
    const html = renderDetail(TARGET_ONLY_IDEA);
    expect(html).not.toContain('level-fix-');
    // The chart's subject is published levels; a pending bracket has none.
    expect(html).not.toContain('data-testid="level-fix-chart"');
    expect(html).not.toContain('data-testid="level-fix-loading"');
  });

  it('still renders the full ladder and R:R once the bracket is published', () => {
    const html = renderDetail(PUBLISHED_IDEA);
    expect(html).not.toContain('data-testid="trade-levels-pending"');
    expect(html).not.toContain(PENDING_COPY);
    expect(html).toContain('>Entry<');
    expect(html).toContain('>Stop<');
    expect(html).toContain('>Target<');
    expect(html).toContain('R:R 1.5');
  });

  it('keeps the detail grid two-column when a pending bracket sits beside evidence', () => {
    const html = renderDetail({ ...TARGET_ONLY_IDEA, evidence: LEVELS_IDEA.evidence });
    expect(html).toContain('data-testid="trade-levels-pending"');
    expect(html).toContain('Market evidence');
    expect(html).toContain('sm:grid-cols-2');
  });

  it('never reserves ladder height or animates the pending state', () => {
    const html = renderDetail({ ...TARGET_ONLY_IDEA, evidence: LEVELS_IDEA.evidence });
    expect(html).not.toContain('sk-shimmer');
    expect(html).not.toContain('animate-');
    expect(html).not.toContain('Skeleton');
    expect(html).not.toContain('min-h-');
    expect(html).not.toContain('aria-busy');
    expect(html).not.toContain('aria-live');
  });
});
