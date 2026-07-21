import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Node-environment test (no jsdom), mirroring components/legacy-spa-redirect.test.tsx:
 * we run the page's data-load effect synchronously by stubbing React's `useEffect`
 * to invoke its callback immediately, and stub `useState` so the resolved tearsheet
 * is committed before render. We then render PerformancePage to a string and assert
 * the loaded OlympusTearsheetView (serif H1 "Olympus") appears — the loading→loaded
 * transition, exercised the same way app/system/page.test.ts asserts its page chrome.
 */
import { buildOlympusTearsheet } from '@/lib/observability-queries';

const sample = buildOlympusTearsheet({
  nav: [{ date: '2026-06-23', nav: 99.32, cash_pct: 25, invested_pct: 75 }],
  decisions: [],
  metrics: null,
  attribution: [],
});

vi.mock('@/lib/observability-queries', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/observability-queries')>(
      '@/lib/observability-queries'
    );
  return { ...actual, fetchOlympusTearsheet: vi.fn(() => Promise.resolve(sample)) };
});

vi.mock('@/components/observability/AttributionTab', () => ({ default: () => null }));
vi.mock('@/components/page-skeleton', () => ({ default: () => null }));

vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react');
  // The page declares useState in source order: [data, setData] then [error, setError].
  // Seed the FIRST useState with the resolved tearsheet (loaded state) and leave the
  // SECOND (error) at its initial null, so the first render is the loaded view.
  let call = 0;
  return {
    ...actual,
    useEffect: (fn: () => void) => fn(),
    useState: <T,>(init: T) => {
      const isFirst = call === 0;
      call += 1;
      return [isFirst ? (sample as unknown as T) : init, vi.fn()] as [T, (v: T) => void];
    },
  };
});

import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import PerformancePage from './page';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('/portfolio/performance route', () => {
  it('renders the Olympus performance command band once data loads', () => {
    const html = renderToStaticMarkup(createElement(PerformancePage));
    expect(html).toContain('data-testid="performance-command-band"');
    expect(html).toContain('>Olympus</h1>');
    expect(html).toContain('AI-intelligence strategy');
    expect(html).toMatch(/Download PDF/);
  });
});
