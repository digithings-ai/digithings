import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';
import { buildOlympusTearsheet } from '@/lib/observability-queries';
import { OlympusTearsheetView } from './OlympusTearsheetView';
import type { TableRow } from '@/lib/database.types';

vi.mock('@/components/observability/AttributionTab', () => ({
  default: () => createElement('div', { 'data-testid': 'attribution' }),
}));

const navRow = (date: string, nav: number): TableRow<'nav_history'> => ({
  date,
  nav,
  cash_pct: 25,
  invested_pct: 75,
});

function html(data: Parameters<typeof OlympusTearsheetView>[0]['data']) {
  return renderToStaticMarkup(createElement(OlympusTearsheetView, { data }));
}

describe('OlympusTearsheetView', () => {
  it('single NAV point → inception card, not a single-dot chart', () => {
    const data = buildOlympusTearsheet({
      nav: [navRow('2026-06-23', 99.32)],
      decisions: [],
      metrics: null,
      attribution: [],
    });
    const out = html(data);
    expect(out).toContain('Olympus'); // serif H1
    expect(out).toMatch(/live since 2026-06-23/);
    expect(out).toMatch(/equity curve accrues daily/);
    // the live equity TimeSeries must NOT render with 1 point
    expect(out).not.toContain('class="ts-line');
  });

  it('0 resolved decisions → in-flight line, not an empty track-record chart', () => {
    const data = buildOlympusTearsheet({
      nav: [navRow('2026-06-23', 99.32)],
      decisions: [
        {
          id: 'q',
          run_id: 'r',
          run_date: '2026-06-23',
          ticker: 'QQQ',
          stance: 'buy',
          conviction: 3,
          thesis: null,
          benchmark: 'SPY',
          holding_days: 10,
          status: 'pending',
          actual_return: null,
          alpha: null,
          reflection: null,
          resolved_at: null,
          created_at: null,
        },
      ],
      metrics: null,
      attribution: [],
    });
    const out = html(data);
    expect(out).toMatch(/1 decision in flight|decisions in flight/);
    expect(out).toMatch(/track record resolves as holding windows close/);
  });

  it('export button is present in all states', () => {
    const data = buildOlympusTearsheet({ nav: [], decisions: [], metrics: null, attribution: [] });
    expect(html(data)).toMatch(/Download PDF|Export/);
  });

  it('≥2 NAV + resolved decisions → renders the equity line and the calibration chart', () => {
    const data = buildOlympusTearsheet({
      nav: [navRow('2026-06-23', 100), navRow('2026-06-24', 102)],
      decisions: [
        {
          id: 'a',
          run_id: 'r',
          run_date: '2026-06-23',
          ticker: 'IJR',
          stance: 'buy',
          conviction: 5,
          thesis: null,
          benchmark: 'SPY',
          holding_days: 10,
          status: 'resolved',
          actual_return: 0.05,
          alpha: 0.04,
          reflection: null,
          resolved_at: null,
          created_at: null,
        },
      ],
      metrics: null,
      attribution: [],
    });
    const out = html(data);
    expect(out).toContain('ts-line'); // equity curve drawn
    expect(out).toMatch(/Conviction calibration/);
    expect(out).toContain('ts-bar'); // SignedBars rendered
  });

  it('uses a flat command band, asymmetric chart workspace, and bounded decision ledger', () => {
    const data = buildOlympusTearsheet({
      nav: [navRow('2026-06-23', 100), navRow('2026-06-24', 102)],
      decisions: [
        {
          id: 'a',
          run_id: 'r',
          run_date: '2026-06-23',
          ticker: 'IJR',
          stance: 'buy',
          conviction: 5,
          thesis: null,
          benchmark: 'SPY',
          holding_days: 10,
          status: 'resolved',
          actual_return: 0.05,
          alpha: 0.04,
          reflection: null,
          resolved_at: null,
          created_at: null,
        },
      ],
      metrics: null,
      attribution: [],
    });
    const out = html(data);

    expect(out).toContain('data-testid="performance-command-band"');
    expect(out).toContain('data-region="performance-chart-grid"');
    expect(out).toContain('data-layout="asymmetric"');
    expect(out).toContain('data-region="decision-ledger"');
    expect(out).not.toContain('glass-card');
  });

  it('≤12 resolved decisions → renders all rows without expand control', () => {
    const decisions = Array.from({ length: 10 }, (_, i) => ({
      id: `d${i}`,
      run_id: 'r',
      run_date: `2026-06-${String(i + 1).padStart(2, '0')}`,
      ticker: `T${i}`,
      stance: 'buy',
      conviction: 3,
      thesis: null,
      benchmark: 'SPY',
      holding_days: 10,
      status: 'resolved' as const,
      actual_return: 0.01,
      alpha: 0.005,
      reflection: null,
      resolved_at: null,
      created_at: null,
    }));
    const data = buildOlympusTearsheet({
      nav: [navRow('2026-06-23', 100), navRow('2026-06-24', 102)],
      decisions,
      metrics: null,
      attribution: [],
    });
    const out = html(data);
    // All 10 tickers should be visible
    expect(out).toContain('T0');
    expect(out).toContain('T9');
    // No expand button when ≤12 rows
    expect(out).not.toMatch(/Show.*older/i);
    expect(out).not.toMatch(/Show.*fewer/i);
  });

  it('>12 resolved decisions → renders 12 most-recent rows + "Show N older" button by default', () => {
    const decisions = Array.from({ length: 20 }, (_, i) => ({
      id: `d${i}`,
      run_id: 'r',
      run_date: `2026-${String(Math.floor(i / 30) + 1).padStart(2, '0')}-${String((i % 30) + 1).padStart(2, '0')}`,
      ticker: `T${i}`,
      stance: 'buy',
      conviction: 3,
      thesis: null,
      benchmark: 'SPY',
      holding_days: 10,
      status: 'resolved' as const,
      actual_return: 0.01,
      alpha: 0.005,
      reflection: null,
      resolved_at: null,
      created_at: null,
    }));
    const data = buildOlympusTearsheet({
      nav: [navRow('2026-06-23', 100), navRow('2026-06-24', 102)],
      decisions,
      metrics: null,
      attribution: [],
    });
    const out = html(data);
    // Newest 12 tickers should be visible (T8 through T19)
    expect(out).toContain('<td>T19</td>');
    expect(out).toContain('<td>T8</td>');
    // Older tickers should NOT be visible by default
    expect(out).not.toContain('<td>T0</td>');
    expect(out).not.toContain('<td>T7</td>');
    // "Show N older" button should be present
    expect(out).toMatch(/Show 8 older/i);
  });
});
