/**
 * Self-contained tests for GET /brief (`brief.ts`, contract §6.3).
 * Fixture expectations verified against the client Brief derivation
 * (`apps/dashboard/app/page.tsx` persisted-vs-overlay split) via scratch parity.
 */
import { describe, expect, it } from 'vitest';

import {
  buildBriefData,
  buildBriefProvenance,
  parseBriefQuery,
  registerBriefRoutes,
  type BriefBook,
} from './brief';

const NAV6 = [
  { date: '2026-08-20', nav: 100, source: 'legacy_nav_history', contract: 'legacy_estimate' },
  {
    date: '2026-08-21',
    nav: 102,
    day_return_pct: 2,
    source: 'legacy_nav_history',
    contract: 'legacy_estimate',
  },
  {
    date: '2026-08-22',
    nav: 101,
    day_return_pct: null,
    source: 'legacy_nav_history',
    contract: 'legacy_estimate',
  },
  {
    date: '2026-08-26',
    nav: 200,
    day_return_pct: null,
    source: 'finalized_accounting',
    contract: 'finalized_accounting',
    series_seam: true,
  },
  {
    date: '2026-08-27',
    nav: 202,
    day_return_pct: null,
    source: 'finalized_accounting',
    contract: 'finalized_accounting',
  },
  {
    date: '2026-08-28',
    nav: 204.04,
    day_return_pct: null,
    source: 'finalized_accounting',
    contract: 'finalized_accounting',
  },
];

function book(overrides: Partial<BriefBook> = {}): BriefBook {
  return {
    navRows: NAV6,
    snapshotDate: '2026-08-28',
    positionDates: ['2026-08-28'],
    positionMetricsAsOf: ['2026-08-27'],
    bookWeightInvestedPct: 35.13,
    metricsInvestedPct: 80,
    metricsAsOf: '2026-08-27',
    live: null,
    ledgerEvents: [
      { date: '2026-08-28', ticker: 'XLV', event: 'TRIM', weight_pct: 4.9, prev_weight_pct: 9.9 },
    ],
    ...overrides,
  };
}

describe('parseBriefQuery', () => {
  it('defaults to auto overlay and echoes pins', () => {
    const parsed = parseBriefQuery(new URLSearchParams('retrieval_pin=abc'));
    expect(parsed).toEqual({
      ok: true,
      query: { asOf: null, retrievalPin: 'abc', overlay: 'auto' },
    });
  });
  it('rejects malformed params with bad_request', () => {
    const oddMonth = new URLSearchParams('asOf=2026-13-99');
    // Shape check only — still YYYY-MM-DD.
    expect(parseBriefQuery(oddMonth).ok).toBe(true);
    expect(parseBriefQuery(new URLSearchParams('asOf=yesterday'))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
    expect(parseBriefQuery(new URLSearchParams('overlay=sometimes'))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
    expect(parseBriefQuery(new URLSearchParams(`retrieval_pin=${'x'.repeat(129)}`))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
  });
});

describe('buildBriefData', () => {
  it('overlay-off serves the persisted path with a finalized badge', () => {
    const data = buildBriefData(book(), 'off');
    expect(data.book_as_of).toBe('2026-08-28');
    expect(data.nav_tip).toEqual({
      date: '2026-08-28',
      nav: 204.04,
      contract: 'finalized_accounting',
    });
    expect(data.day_return_pct).toBeCloseTo(1.0099, 4);
    expect(data.since_inception_pct).toBeCloseTo(3.0402, 4);
    expect(data.overlay).toEqual({
      active: false,
      live_vs_mark_pct: 0,
      badge: 'finalized accounting',
    });
    expect(data.invested_pct).toBe(35.13);
    expect(data.session_events).toHaveLength(1);
  });
  it('overlay engages only on a nonzero live move and wears live marks', () => {
    const live = {
      liveVsMarkPct: 0.2,
      sinceInceptionPct: 3.3,
      sinceInceptionStartDate: '2026-08-20',
      dayReturnPct: 1.2,
      priceAsOfDate: '2026-08-28',
      excessReturnPct: 0.3,
      benchmarkTicker: 'SPY',
    };
    const on = buildBriefData(book({ live }), 'auto');
    expect(on.overlay).toEqual({ active: true, live_vs_mark_pct: 0.2, badge: 'live marks' });
    expect(on.since_inception_pct).toBe(3.3);
    expect(on.day_return_pct).toBe(1.2);
    const forced = buildBriefData(book({ live: { ...live, liveVsMarkPct: 0 } }), 'auto');
    expect(forced.overlay.active).toBe(false);
    expect(forced.since_inception_pct).toBeCloseTo(3.0402, 4);
    const off = buildBriefData(book({ live }), 'off');
    expect(off.overlay.active).toBe(false);
    expect(off.since_inception_pct).toBeCloseTo(3.0402, 4);
  });
  it('nulls day return when the tip crosses a NAV seam', () => {
    const seamed = [
      { date: '2026-08-27', nav: 202, source: 'legacy_nav_history', contract: 'legacy_estimate' },
      {
        date: '2026-08-28',
        nav: 204.04,
        day_return_pct: 5.5,
        source: 'finalized_accounting',
        contract: 'finalized_accounting',
        series_seam: true,
      },
    ];
    const data = buildBriefData(book({ navRows: seamed }), 'off');
    expect(data.day_return_pct).toBeNull();
    expect(data.since_inception_pct).not.toBeNull();
  });
  it('honest empty session events when the book date has no moves', () => {
    const data = buildBriefData(book({ ledgerEvents: [] }), 'off');
    expect(data.session_events).toEqual([]);
  });
});

describe('buildBriefProvenance', () => {
  it('badges tip source, contract, seam and marks', () => {
    expect(buildBriefProvenance(book())).toEqual({
      source: 'public_accounting_nav_history',
      tip_date: '2026-08-28',
      contract: 'finalized_accounting',
      seam: false,
      marks: 'stored',
    });
    expect(
      buildBriefProvenance(book({ positionMetricsAsOf: ['2026-08-27', null] })).marks,
    ).toBe('unavailable');
  });
});

describe('registerBriefRoutes', () => {
  it('serves the envelope and fails closed on missing book', async () => {
    const handlers = new Map<string, (req: Request) => Promise<Response>>();
    registerBriefRoutes((path, handler) => handlers.set(path, handler), {
      loadBriefBook: async (asOf) => (asOf === '2020-01-01' ? null : book()),
    });
    const ok = await handlers.get('/brief')!(new Request('https://api.test/brief?overlay=off'));
    expect(ok.status).toBe(200);
    const body = (await ok.json()) as {
      data: { book_as_of: string };
      as_of: string;
      retrieval_pin: null;
      provenance: { contract: string };
    };
    expect(body.data.book_as_of).toBe('2026-08-28');
    expect(body.as_of).toBe('2026-08-28');
    expect(body.provenance.contract).toBe('finalized_accounting');
    const missing = await handlers.get('/brief')!(
      new Request('https://api.test/brief?asOf=2020-01-01'),
    );
    expect(missing.status).toBe(404);
    const missingBody = (await missing.json()) as { error: { code: string } };
    expect(missingBody.error.code).toBe('not_found');
    const bad = await handlers.get('/brief')!(new Request('https://api.test/brief?overlay=x'));
    expect(bad.status).toBe(400);
  });
});
