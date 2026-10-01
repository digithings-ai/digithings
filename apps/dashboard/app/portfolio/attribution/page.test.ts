import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const sample = {
  attribution: [],
  attributionDate: '2026-06-23',
  decisions: [
    {
      id: 'd1', run_id: 'r', run_date: '2026-06-23', ticker: 'NVDA', stance: 'buy', conviction: 3,
      thesis: 't', benchmark: 'SPY', holding_days: 5, status: 'resolved', actual_return: 0.04,
      alpha: 0.02, reflection: 'r', resolved_at: '2026-06-30T16:00:00Z', created_at: '2026-06-23T16:00:00Z',
    },
  ],
};

vi.mock('@/lib/observability-queries', () => ({
  fetchPortfolioAttribution: vi.fn(() => Promise.resolve(sample)),
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
  it('renders the Decisions view in place with an h1 and the edge pane active', () => {
    const html = renderToStaticMarkup(createElement(AttributionPage));

    expect(html).toContain('<h1 class="sr-only">Attribution</h1>');
    expect(html).toContain('data-testid="decisions-view"');
    expect(html).toContain('Decision monitor');
    expect(html).toContain('Decision edge over time');
    expect(html).toContain('2026-06-23');
    expect(html).toContain('>Audit<');
    // Theses live on /portfolio?tab=decisions, not here.
    expect(html).not.toContain('>Theses<');
    expect(html).not.toContain('Position decomposition');
  });
});
