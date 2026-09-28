import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Node-environment test (no jsdom), mirroring components/legacy-spa-redirect.test.tsx:
 * we run the page's data-load effect synchronously by stubbing React's `useEffect`
 * to invoke its callback immediately, and stub `useState` so the resolved tearsheet
 * is committed before render. We then render PerformancePage to a string and assert
 * the loaded PerformanceTearsheetView (H1 "Performance") appears — the loading→loaded
 * transition, exercised the same way app/system/page.test.ts asserts its page chrome.
 */
import { buildPerformanceTearsheet } from '@/lib/observability-queries';
import type { PerformanceSsotMeta } from '@/lib/performance-ssot';

const sample = buildPerformanceTearsheet({
  nav: [{ date: '2026-06-23', nav: 99.32, cash_pct: 25, invested_pct: 75 }],
  positions: [],
  metrics: null,
  attribution: [],
  accountingNav: [
    {
      date: '2026-06-23',
      nav: 99.32,
      cash_pct: 25,
      invested_pct: 75,
      day_return_pct: 0,
      source: 'legacy_nav_history',
      contract: 'legacy_estimate',
    },
  ],
});

const sampleSsot: PerformanceSsotMeta = {
  navContract: 'legacy_estimate',
  navAsOf: '2026-06-23',
  tipDayReturnPct: 0,
  tipInvestedPct: 75,
  tipCashPct: 25,
  metricsAsOf: null,
  metricsLagDays: null,
  metricsLagging: false,
  bookAsOf: '2026-06-23',
  marksUnstamped: false,
  investedDefinition: 'accounting_nav_tip',
};

vi.mock('@/lib/observability-queries', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/observability-queries')>(
      '@/lib/observability-queries'
    );
  return {
    ...actual,
    getPerformanceBundle: vi.fn(() =>
      Promise.resolve({ tearsheet: sample, ssot: sampleSsot })
    ),
    fetchPerformanceTearsheet: vi.fn(() => Promise.resolve(sample)),
  };
});

vi.mock('@/components/observability/AttributionTab', () => ({ default: () => null }));
vi.mock('@/components/page-skeleton', () => ({ default: () => null }));
vi.mock('@/lib/use-entitlement', () => ({
  useCan: () => true,
  usePlanTier: () => 'enterprise',
}));

let stateCall = 0;
vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react');
  // PerformancePage useState order: data → ssot → error.
  return {
    ...actual,
    useEffect: (fn: () => void) => fn(),
    useState: <T,>(init: T) => {
      stateCall += 1;
      if (stateCall === 1) return [sample as unknown as T, vi.fn()] as [T, (v: T) => void];
      if (stateCall === 2) return [sampleSsot as unknown as T, vi.fn()] as [T, (v: T) => void];
      return [init, vi.fn()] as [T, (v: T) => void];
    },
  };
});

import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import PerformancePage from './page';

beforeEach(() => {
  stateCall = 0;
  vi.clearAllMocks();
});

describe('/portfolio/performance route', () => {
  it('renders the persisted Performance view once data loads', () => {
    const html = renderToStaticMarkup(createElement(PerformancePage));
    expect(html).toContain('Performance');
    expect(html).toContain('Download performance tear sheet as PDF');
    expect(html).toContain('legacy estimate');
  });
});
