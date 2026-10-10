import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api-client';

const digiquant = vi.hoisted(() => ({
  getBrief: vi.fn(),
  getPortfolio: vi.fn(),
  getAllocations: vi.fn(),
  getTable: vi.fn(),
}));

const market = vi.hoisted(() => ({ fetchMarketCloses: vi.fn() }));
const bars = vi.hoisted(() => ({ fetchVelaBars: vi.fn() }));

vi.mock('@/lib/desk/digiquant', () => digiquant);
vi.mock('@/lib/market-data', () => market);
vi.mock('@/lib/vela-bars', async () => {
  const actual = await vi.importActual<typeof import('@/lib/vela-bars')>('@/lib/vela-bars');
  return { ...actual, fetchVelaBars: bars.fetchVelaBars };
});

import { loadBriefSnapshot } from './load';

const briefData = {
  book_as_of: '2026-09-30',
  nav_tip: { date: '2026-09-30', nav: null, contract: 'finalized_accounting' },
  day_return_pct: null,
  since_inception_pct: null,
  since_inception_start_date: null,
  overlay: { active: false, live_vs_mark_pct: 0, badge: 'legacy estimate' },
  invested_pct: 40,
  session_events: [],
};

beforeEach(() => {
  digiquant.getBrief.mockReset();
  digiquant.getPortfolio.mockReset();
  digiquant.getAllocations.mockReset();
  digiquant.getTable.mockReset();
  market.fetchMarketCloses.mockReset();
  bars.fetchVelaBars.mockReset();
});

describe('loadBriefSnapshot', () => {
  it('calls the digiquant house routes from the path table', async () => {
    digiquant.getBrief.mockResolvedValue({
      data: briefData,
      asOf: '2026-09-30',
      retrievalPin: null,
      provenance: null,
    });
    digiquant.getPortfolio.mockResolvedValue({
      data: {
        book_as_of: '2026-09-30',
        nav_tip: null,
        seam: { crosses_nav_seam: false, lag_days: null, lag_direction: null },
        invested: { kpi_pct: 40, envelope_pct: 40, cash_pct: 60, definition: 'book_weights' },
        positions: [{ ticker: 'SPY', weight_pct: 40, scaled_weight_pct: 40, is_cash: false }],
      },
      asOf: null,
      retrievalPin: null,
      provenance: null,
    });
    digiquant.getAllocations.mockResolvedValue({
      data: {
        book_as_of: '2026-09-30',
        invested_pct: 40,
        cash_pct: 60,
        invested_definition: 'book_weights',
        marks_unstamped: false,
        rows: [
          {
            ticker: 'SPY',
            weight_pct: 40,
            scaled_weight_pct: 40,
            entry_price: 1,
            current_price: 2,
            unrealized_pct: null,
            marks: 'stored',
            marks_as_of: '2026-09-30',
          },
        ],
      },
      asOf: null,
      retrievalPin: null,
      provenance: null,
    });
    digiquant.getTable.mockImplementation(async (table: string) => {
      if (table === 'theses') return [{ thesis_id: 'T-1', date: '2026-09-30', name: 'A' }];
      if (table === 'run_health') {
        return [{ run_id: 'run-1', run_date: '2026-09-30', created_at: '2026-09-30T00:00:00Z' }];
      }
      if (table === 'run_event_trace') return [];
      throw new Error(`unexpected table ${table}`);
    });
    market.fetchMarketCloses.mockResolvedValue([]);
    bars.fetchVelaBars.mockResolvedValue({
      bars: [{ t: 1, o: 1, h: 1, l: 1, c: 1 }],
      symbol: 'SPY',
      timeframe: '1d',
      source: 'digiquant',
      stale: false,
      delayNote: null,
    });

    const snapshot = await loadBriefSnapshot('1d');

    expect(digiquant.getBrief).toHaveBeenCalledWith({ overlay: 'auto' });
    expect(digiquant.getPortfolio).toHaveBeenCalledWith();
    expect(digiquant.getAllocations).toHaveBeenCalledWith({ includeMarks: true });
    expect(digiquant.getTable).toHaveBeenCalledWith('theses', {
      eq: { date: '2026-09-30' },
      limit: 100,
    });
    expect(digiquant.getTable).toHaveBeenCalledWith('run_health', {
      order: 'created_at.desc',
      limit: 20,
    });
    expect(digiquant.getTable).toHaveBeenCalledWith('run_event_trace', {
      eq: { run_id: 'run-1' },
      limit: 1,
    });
    expect(market.fetchMarketCloses).toHaveBeenCalledWith(['SPY'], '2026-09-16', '2026-09-30');
    expect(bars.fetchVelaBars).toHaveBeenCalledWith('SPY', '1d');
    expect(snapshot.chart.status).toBe('ok');
    expect(snapshot.chart.symbol).toBe('SPY');
  });

  it('does not read theses or bars when the book is missing', async () => {
    const missing = new ApiError(404, 'not_found', 'no committed book');
    digiquant.getBrief.mockRejectedValue(missing);
    digiquant.getPortfolio.mockRejectedValue(missing);
    digiquant.getAllocations.mockRejectedValue(missing);
    digiquant.getTable.mockResolvedValue([]);

    const snapshot = await loadBriefSnapshot('1d');

    expect(snapshot.brief.status).toBe('empty');
    expect(snapshot.thesesSkipped).toBe(true);
    const tables = digiquant.getTable.mock.calls.map((call) => call[0]);
    expect(tables).toContain('run_health');
    expect(tables).not.toContain('theses');
    expect(bars.fetchVelaBars).not.toHaveBeenCalled();
    expect(snapshot.chart.symbol).toBeNull();
  });

  it('withholds a stub NAV envelope instead of painting it', async () => {
    digiquant.getBrief.mockResolvedValue({
      data: {
        ...briefData,
        nav_tip: { date: '2026-08-28', nav: 204.04, contract: 'finalized_accounting' },
        since_inception_pct: 3.040191838399986,
      },
      asOf: '2026-08-28',
      retrievalPin: null,
      provenance: null,
    });
    digiquant.getPortfolio.mockResolvedValue({
      data: {
        book_as_of: '2026-09-24',
        nav_tip: { date: '2026-09-24', nav: 99.909, contract: 'legacy_estimate' },
        positions: [],
      },
      asOf: null,
      retrievalPin: null,
      provenance: null,
    });
    digiquant.getAllocations.mockResolvedValue({
      data: { book_as_of: '2026-09-24', rows: [], contract: 'legacy_estimate' },
      asOf: null,
      retrievalPin: null,
      provenance: null,
    });
    digiquant.getTable.mockResolvedValue([]);
    market.fetchMarketCloses.mockResolvedValue([]);

    const snapshot = await loadBriefSnapshot('1d');

    expect(snapshot.brief.status).toBe('error');
    expect(snapshot.brief.message).toContain('stub envelope');
    expect(snapshot.portfolio.status).toBe('error');
    expect(snapshot.allocations.status).toBe('error');
    expect(snapshot.thesesSkipped).toBe(true);
    expect(snapshot.chart.symbol).toBeNull();
    expect(bars.fetchVelaBars).not.toHaveBeenCalled();
    expect(market.fetchMarketCloses).not.toHaveBeenCalled();
  });

  it('names an unreachable API instead of the browser fetch error', async () => {
    const down = new TypeError('Failed to fetch');
    digiquant.getBrief.mockRejectedValue(down);
    digiquant.getPortfolio.mockRejectedValue(down);
    digiquant.getAllocations.mockRejectedValue(down);
    digiquant.getTable.mockRejectedValue(down);

    const snapshot = await loadBriefSnapshot('1d');

    expect(snapshot.brief.status).toBe('error');
    expect(snapshot.brief.message).toBe('The official API could not be reached.');
    expect(snapshot.portfolio.message).toBe('The official API could not be reached.');
    expect(snapshot.runHealth.message).toBe('The official API could not be reached.');
  });
});
