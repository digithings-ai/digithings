import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { FxTradeIdeaRow } from '@/lib/twelve-x/types';
import LevelFixSection, { fixesForPair } from './LevelFixSection';
import { getFxFixSeries } from '@/lib/twelve-x/fetch';

vi.mock('@/lib/twelve-x/fetch', () => ({
  getFxFixSeries: vi.fn(),
}));

const mockedFixSeries = vi.mocked(getFxFixSeries);

beforeEach(() => {
  mockedFixSeries.mockReset();
});

describe('LevelFixSection', () => {
  it('renders a loading state before the client-side fix fetch resolves', () => {
    const idea: FxTradeIdeaRow = {
      run_date: '2026-06-12',
      rank: 1,
      pair: 'EUR/USD',
      direction: 'long',
      title: 'EUR/USD long',
      thesis: '',
      catalyst: '',
      levels: [],
      citations: [],
      as_of: '2026-06-26T00:00:00Z',
    };
    const html = renderToStaticMarkup(createElement(LevelFixSection, { idea }));
    // Effects never run under static markup, so the fetch never resolves here.
    expect(html).toContain('data-testid="level-fix-loading"');
    expect(html).toContain('Loading fix series');
  });

  it('does not pin a transient failure in the cache — the next call retries', async () => {
    mockedFixSeries.mockRejectedValueOnce(new Error('flaky'));
    const first = await fixesForPair('EUR/USD', 90);
    expect(first).toEqual({ 'EUR/USD': [] });
    mockedFixSeries.mockResolvedValueOnce({ 'EUR/USD': [] });
    await fixesForPair('EUR/USD', 90);
    // Rejected once + retried once: no permanently-cached empty series.
    expect(mockedFixSeries).toHaveBeenCalledTimes(2);
  });

  it('shares one fetch for the same pair+window', async () => {
    mockedFixSeries.mockResolvedValue({ 'GBP/USD': [] });
    const [a, b] = await Promise.all([
      fixesForPair('GBP/USD', 90),
      fixesForPair('GBP/USD', 90),
    ]);
    expect(mockedFixSeries).toHaveBeenCalledTimes(1);
    expect(a).toBe(b);
  });

  it('passes an idea-age-covering window, not the bare 90d default', async () => {
    mockedFixSeries.mockResolvedValue({ 'USD/JPY': [] });
    await fixesForPair('USD/JPY', 400);
    expect(mockedFixSeries).toHaveBeenCalledWith(['USD/JPY'], 400);
  });
});
