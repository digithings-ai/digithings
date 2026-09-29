/**
 * Self-contained tests for GET /kpis/live (`kpis-live.ts`, contract §6.5).
 * Math verified against `computeLivePerformanceKpis` (packages/ui) via scratch parity.
 */
import { describe, expect, it } from 'vitest';

import {
  buildLiveData,
  computeLiveVsMarkPct,
  dayReturnAnchorNav,
  derivePriceAsOfDate,
  navHistoryForLiveOverlap,
  parseLiveQuery,
  registerLiveRoutes,
  type LiveBook,
} from './kpis-live';

const NAV6 = [
  { date: '2026-08-20', nav: 100 },
  { date: '2026-08-21', nav: 102 },
  { date: '2026-08-22', nav: 101 },
  { date: '2026-08-26', nav: 200 },
  { date: '2026-08-27', nav: 202 },
  { date: '2026-08-28', nav: 204.04 },
];

const SPY6 = [
  { date: '2026-08-20', price: 500 },
  { date: '2026-08-21', price: 505 },
  { date: '2026-08-22', price: 502.5 },
  { date: '2026-08-26', price: 510 },
  { date: '2026-08-27', price: 512 },
  { date: '2026-08-28', price: 515 },
];

const POSITIONS: LiveBook['positions'] = [
  {
    ticker: 'XLV',
    weightPct: 20,
    markPrice: 100,
    effectivePrice: 101,
    isLive: true,
    metricsAsOf: '2026-08-27',
    livePriceDate: '2026-08-28',
  },
  {
    ticker: 'DBO',
    weightPct: 5,
    markPrice: 50,
    effectivePrice: 50,
    isLive: false,
    metricsAsOf: '2026-08-27',
    livePriceDate: null,
  },
];

describe('live math helpers', () => {
  it('weights the live move by book weight (DBO flat, XLV +1% on 20%)', () => {
    expect(computeLiveVsMarkPct(POSITIONS)).toBeCloseTo(0.2, 10);
    expect(computeLiveVsMarkPct([])).toBe(0);
  });
  it('prefers the live date for footnotes, falls back to marks', () => {
    expect(derivePriceAsOfDate(POSITIONS)).toBe('2026-08-28');
    expect(
      derivePriceAsOfDate(POSITIONS.map((p) => ({ ...p, isLive: false, livePriceDate: null }))),
    ).toBe('2026-08-27');
    expect(derivePriceAsOfDate([])).toBeNull();
  });
  it('anchors day return on the latest close when marks run ahead', () => {
    expect(dayReturnAnchorNav(NAV6, '2026-08-29')).toBe(204.04);
    expect(dayReturnAnchorNav(NAV6, '2026-08-28')).toBe(202);
    expect(dayReturnAnchorNav([], '2026-08-28')).toBeNull();
  });
  it('keeps every accounting row when appending a live tip', () => {
    const extended = navHistoryForLiveOverlap(NAV6, '2026-08-29', 205);
    expect(extended).toHaveLength(7);
    expect(extended.at(-1)).toEqual({ date: '2026-08-29', nav: 205 });
    expect(navHistoryForLiveOverlap(NAV6, '2026-08-28', 204.5).at(-1)).toEqual({
      date: '2026-08-28',
      nav: 204.5,
    });
  });
});

describe('parseLiveQuery', () => {
  it('accepts an empty query and rejects asOf + long pins', () => {
    expect(parseLiveQuery(new URLSearchParams(''))).toEqual({ ok: true, retrievalPin: null });
    expect(parseLiveQuery(new URLSearchParams('asOf=2026-08-28'))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
    expect(parseLiveQuery(new URLSearchParams(`retrieval_pin=${'x'.repeat(129)}`))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
  });
});

describe('buildLiveData', () => {
  it('snapshots live marks with overlay eligibility', () => {
    const data = buildLiveData({
      positions: POSITIONS,
      navHistory: NAV6,
      benchmarkHistory: SPY6,
      benchmarkTicker: 'SPY',
    });
    expect(data.quote_date).toBe('2026-08-28');
    expect(data.live_vs_mark_pct).toBeCloseTo(0.2, 10);
    expect(data.day_return_live_pct).toBeCloseTo(1.2119, 4);
    expect(data.overlay_eligible).toBe(true);
    expect(data.universe).toEqual(['DBO', 'XLV']);
    expect(data.excess_live_pct).not.toBeNull();
  });
  it('stays ineligible when marks never moved or are all NULL', () => {
    const flat = buildLiveData({
      positions: POSITIONS.map((p) => ({ ...p, isLive: false, effectivePrice: p.markPrice })),
      navHistory: NAV6,
      benchmarkHistory: SPY6,
      benchmarkTicker: 'SPY',
    });
    expect(flat.live_vs_mark_pct).toBe(0);
    expect(flat.overlay_eligible).toBe(false);
    const unmarked = buildLiveData({
      positions: POSITIONS.map((p) => ({
        ...p,
        markPrice: null,
        effectivePrice: 101,
        isLive: true,
      })),
      navHistory: NAV6,
      benchmarkHistory: SPY6,
      benchmarkTicker: 'SPY',
    });
    expect(unmarked.overlay_eligible).toBe(false);
  });
});

describe('registerLiveRoutes', () => {
  it('serves the snapshot with market_api provenance', async () => {
    const handlers = new Map<string, (req: Request) => Promise<Response>>();
    registerLiveRoutes((path, handler) => handlers.set(path, handler), {
      loadLiveBook: async () => ({
        positions: POSITIONS,
        navHistory: NAV6,
        benchmarkHistory: SPY6,
        benchmarkTicker: 'SPY',
      }),
    });
    const res = await handlers.get('/kpis/live')!(new Request('https://api.test/kpis/live'));
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      data: { overlay_eligible: boolean };
      provenance: { source: string; contract: null };
    };
    expect(body.data.overlay_eligible).toBe(true);
    expect(body.provenance.source).toBe('market_api');
    expect(body.provenance.contract).toBeNull();
  });
});
