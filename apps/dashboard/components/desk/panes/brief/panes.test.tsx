import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { BriefApiData, PortfolioApiData } from '@/lib/api-types';
import type { AllocationsData, DigiquantRead } from '@/lib/desk/digiquant';
import { EM_DASH } from './format';
import { BriefDeskView } from './BriefDesk';
import { buildBriefPanes, focusSymbol, type BriefSnapshot } from './model';

function read<T>(data: T): DigiquantRead<T> {
  return { data, asOf: '2026-09-30', retrievalPin: 'pin-1', provenance: null };
}

const brief: BriefApiData = {
  book_as_of: '2026-09-30',
  nav_tip: { date: '2026-09-30', nav: null, contract: 'legacy_estimate' },
  day_return_pct: null,
  since_inception_pct: 1.25,
  since_inception_start_date: '2026-08-20',
  overlay: { active: true, live_vs_mark_pct: 0.2, badge: 'finalized accounting' },
  invested_pct: 80,
  session_events: [],
};

const portfolio: PortfolioApiData = {
  book_as_of: '2026-09-30',
  nav_tip: null,
  seam: { crosses_nav_seam: false, lag_days: null, lag_direction: null },
  invested: { kpi_pct: 80, envelope_pct: 80, cash_pct: 20, definition: 'accounting_nav_tip' },
  positions: [
    { ticker: 'XLK', weight_pct: 40, scaled_weight_pct: 40, is_cash: false },
    { ticker: 'CASH', weight_pct: 20, scaled_weight_pct: 20, is_cash: true },
    { ticker: 'DBC', weight_pct: null, scaled_weight_pct: null, is_cash: false },
  ],
};

const allocations: AllocationsData = {
  book_as_of: '2026-09-30',
  invested_pct: 80,
  cash_pct: 20,
  invested_definition: 'accounting_nav_tip',
  marks_unstamped: true,
  rows: [
    {
      ticker: 'XLK',
      weight_pct: 40,
      scaled_weight_pct: 40,
      entry_price: 100,
      current_price: 110,
      unrealized_pct: null,
      marks: 'stored',
      marks_as_of: '2026-09-30',
    },
    {
      ticker: 'DBC',
      weight_pct: 5,
      scaled_weight_pct: 5,
      entry_price: null,
      current_price: null,
      unrealized_pct: null,
      marks: 'unavailable',
      marks_as_of: null,
    },
  ],
};

function snapshot(): BriefSnapshot {
  return {
    brief: { status: 'ok', data: read(brief) },
    portfolio: { status: 'ok', data: read(portfolio) },
    allocations: { status: 'ok', data: read(allocations) },
    thesesSkipped: false,
    theses: {
      status: 'ok',
      data: [
        {
          thesis_id: 'T-1',
          date: '2026-09-30',
          name: 'Breadth',
          status: 'active',
          notes: 'At the floor',
          invalidation: 'Five sessions under 40%',
        },
        {
          thesis_id: 'OLD',
          date: '2026-01-01',
          name: 'Stale',
          status: 'active',
          notes: 'ignore',
          invalidation: 'not today',
        },
      ],
    },
    runHealth: {
      status: 'ok',
      data: [
        {
          run_id: 'r1',
          run_date: '2026-09-30',
          run_type: 'delta',
          status: 'succeeded',
          segments_ok: 15,
          segments_carried: 2,
          segments_failed: 0,
          created_at: '2026-09-30T20:00:00Z',
        },
      ],
    },
    trace: 'none',
    closes: [
      { date: '2026-09-29', ticker: 'XLK', close: 100 },
      { date: '2026-09-30', ticker: 'XLK', close: 105 },
    ],
    chart: {
      status: 'empty',
      symbol: 'XLK',
      bars: [],
      delayNote: null,
    },
  };
}

describe('Brief panes', () => {
  it('focuses the largest non-cash weight and skips null weights', () => {
    expect(focusSymbol(portfolio.positions)).toBe('XLK');
    expect(
      focusSymbol([{ ticker: 'DBC', weight_pct: null, scaled_weight_pct: null, is_cash: false }]),
    ).toBeNull();
  });

  it('shows chrome paths, house figures, and no second KPI band', () => {
    const panes = buildBriefPanes(snapshot(), '1d');
    const html = renderToStaticMarkup(createElement(BriefDeskView, { panes }));

    for (const path of [
      '/house/brief',
      '/house/brief/signals',
      '/house/brief/book',
      '/house/brief/movers',
      '/house/brief/breaks',
      '/house/brief/gloomberg',
      '/house/brief/luxalgo',
      '/house/brief/run',
    ]) {
      expect(html).toContain(`data-chrome-path="${path}"`);
    }

    expect(html).toContain('data-testid="brief-provenance"');
    expect(html).toContain('live marks');
    expect(html).not.toContain('finalized accounting');
    expect(html).toMatch(new RegExp(`data-testid="brief-decision-day"[^>]*>${EM_DASH}<`));
    expect(html).toContain('+1.25%');
    expect(html).not.toContain('brief-kpi-hero');
    expect(html).not.toContain('1,011,846');

    expect(html).toContain('T-1');
    expect(html).not.toContain('>OLD<');
    expect(html).toContain('Five sessions under 40%');
    expect(html).not.toContain('>CASH<');

    expect(html).toContain('data-testid="mover-XLK"');
    const dbc = html.match(/data-testid="mover-DBC"[\s\S]*?<\/tr>/);
    expect(dbc?.[0]).toContain(EM_DASH);
    expect(dbc?.[0]).not.toContain('0.00%');
    expect(html).not.toContain('not today');

    expect(html).toContain('Layout placeholder. Not a Gloomberg feed.');
    expect(html).toContain('No tape headlines.');
    expect(html).not.toContain('Revision breadth');
    expect(html).toContain('No series is drawn in this state.');
    expect(html).not.toContain('610.40');
    expect(html).toContain('LuxAlgo · XLK');
    expect(html).toContain('succeeded');
  });

  it('withholds a failed book instead of printing closes', () => {
    const failed: BriefSnapshot = {
      ...snapshot(),
      brief: { status: 'error', message: 'upstream_empty' },
      allocations: { status: 'error', message: 'upstream_empty' },
      chart: { status: 'empty', symbol: null, bars: [], delayNote: null },
    };
    const html = renderToStaticMarkup(
      createElement(BriefDeskView, { panes: buildBriefPanes(failed, '1d') }),
    );
    expect(html).toContain('Withheld. The run failed.');
    expect(html).toContain('The quote strip stays in the brief layout. This state does not print closes.');
    expect(html).not.toContain('110.00');
    expect(html).toContain('No book symbol to chart.');
  });
});
