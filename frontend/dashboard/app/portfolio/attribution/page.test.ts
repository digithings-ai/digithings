import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const sample = {
  attribution: [
    {
      id: 'nvda-1',
      date: '2026-06-23',
      ticker: 'NVDA',
      sector_bucket: 'Technology',
      weight_pct: 12,
      position_return_pct: 3,
      benchmark_return_pct: 1,
      contribution_pct: 0.36,
      selection_effect_pct: 0.24,
      allocation_effect_pct: null,
      total_attribution_pct: 0.24,
      metrics_as_of: '2026-06-23',
      created_at: '2026-06-23T12:00:00Z',
    },
  ],
  attributionDate: '2026-06-23',
  decisions: [],
};

vi.mock('@/lib/observability-queries', () => ({
  fetchPortfolioAttribution: vi.fn(() => Promise.resolve(sample)),
}));

vi.mock('@/components/observability/AttributionTab', () => ({
  default: ({ date }: { date: string | null }) => createElement('div', null, `Position decomposition ${date}`),
}));

vi.mock('@/components/page-skeleton', () => ({ default: () => null }));
vi.mock('@/lib/use-entitlement', () => ({
  useCan: () => true,
  usePlanTier: () => 'enterprise',
}));

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react');
  let call = 0;
  return {
    ...actual,
    useEffect: (fn: () => void) => fn(),
    useState: <T,>(initial: T) => {
      const isFirst = call === 0;
      call += 1;
      return [isFirst ? (sample as unknown as T) : initial, vi.fn()] as [T, (value: T) => void];
    },
  };
});

import AttributionPage from './page';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('/portfolio/attribution route', () => {
  it('renders the three-view workspace with decision effectiveness active', () => {
    const html = renderToStaticMarkup(createElement(AttributionPage));

    expect(html).toContain('Attribution');
    expect(html).toContain('Decision effectiveness');
    expect(html).toContain('Book attribution');
    expect(html).toContain('Audit');
    expect(html).toContain('Decision monitor');
    expect(html).toContain('As of');
    expect(html).toContain('2026-06-23');
    expect(html).not.toContain('Position decomposition 2026-06-23');
    expect(html).not.toContain('Portfolio intelligence');
    expect(html).not.toContain(
      'Monitor decision edge, trace portfolio drivers, and inspect the underlying record.'
    );
  });
});