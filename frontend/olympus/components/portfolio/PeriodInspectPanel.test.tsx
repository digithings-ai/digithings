import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('next/link', () => ({
  default: (p: { href?: string; children?: unknown }) =>
    createElement('a', { href: p.href }, p.children),
}));

const fetchPeriodStatusRows = vi.fn();

vi.mock('@/lib/period-status', async () => {
  const actual = await vi.importActual<typeof import('@/lib/period-status')>('@/lib/period-status');
  return {
    ...actual,
    fetchPeriodStatusRows: (...args: unknown[]) => fetchPeriodStatusRows(...args),
  };
});

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react');
  let call = 0;
  return {
    ...actual,
    useEffect: (fn: () => void) => fn(),
    useState: <T,>(init: T) => {
      const isFirst = call === 0;
      call += 1;
      if (isFirst) {
        return [{ kind: 'empty' } as unknown as T, vi.fn()] as [T, (v: T) => void];
      }
      return [init, vi.fn()] as [T, (v: T) => void];
    },
  };
});

import PeriodInspectPanel from './PeriodInspectPanel';

beforeEach(() => {
  vi.clearAllMocks();
  fetchPeriodStatusRows.mockResolvedValue({ kind: 'empty' });
});

describe('PeriodInspectPanel (#2652)', () => {
  it('prefers public tip view contract and shows empty evidence without inventing rows', () => {
    const html = renderToStaticMarkup(createElement(PeriodInspectPanel));
    expect(html).toContain('data-testid="period-inspect-panel"');
    expect(html).toContain('public_accounting_period_status');
    expect(html).toContain('Empty evidence');
    expect(html).toContain('data-period-state="empty_public_period_status"');
    expect(html).toContain('olympus_accounting_');
    expect(html).toContain('/portfolio/performance');
    expect(html).not.toContain('opening_equity');
  });
});
