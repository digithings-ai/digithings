import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: ({ children, href, className }: { children?: unknown; href?: string; className?: string }) =>
    createElement('a', { href, className }, children),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/portfolio/ledger',
}));

vi.mock('@/components/portfolio/PortfolioSectionNav', () => ({
  default: () => createElement('nav', { 'data-testid': 'section-nav' }),
}));

vi.mock('@/components/page-skeleton', () => ({
  default: () => createElement('div', { 'data-testid': 'page-skeleton' }),
}));

vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: vi.fn(() => ({
    data: null,
    loading: true,
    error: null,
    dbStatus: 'ok',
  })),
}));

import PortfolioLedgerPage from '@/app/portfolio/ledger/page';
import { useDashboard } from '@/lib/dashboard-context';

describe('PortfolioLedgerPage tier gate', () => {
  it('Observer: LockedSurface before loading (fail-closed; never PageSkeleton)', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: null,
      loading: true,
      error: null,
      dbStatus: 'ok',
    } as ReturnType<typeof useDashboard>);

    const html = renderToStaticMarkup(
      createElement(PortfolioLedgerPage, { tier: 'free' }),
    );
    expect(html).toContain('ledger-locked');
    expect(html).toContain('locked-surface');
    expect(html).not.toContain('page-skeleton');
    expect(html).not.toContain('HoldingsActivityTable');
  });

  it('Observer: LockedSurface even when dashboard already resolved empty', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: { position_events: [] },
      loading: false,
      error: null,
      dbStatus: 'ok',
    } as unknown as ReturnType<typeof useDashboard>);

    const html = renderToStaticMarkup(
      createElement(PortfolioLedgerPage, { tier: 'free' }),
    );
    expect(html).toContain('locked-surface');
    expect(html).not.toContain('No position events recorded yet');
  });

  it('Baseline: loads body (skeleton while dashboard loading)', () => {
    vi.mocked(useDashboard).mockReturnValue({
      data: null,
      loading: true,
      error: null,
      dbStatus: 'ok',
    } as ReturnType<typeof useDashboard>);

    const html = renderToStaticMarkup(
      createElement(PortfolioLedgerPage, { tier: 'baseline' }),
    );
    expect(html).toContain('page-skeleton');
    expect(html).not.toContain('locked-surface');
  });
});
