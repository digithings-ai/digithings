import { createElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { BenchmarkHistoryMap } from '@/lib/types';
import TopAssetsPulse from './top-assets-pulse';

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => createElement('div', null, children),
  LineChart: ({ children }: { children: ReactNode }) => createElement('svg', null, children),
  Line: () => createElement('path'),
  YAxis: () => null,
}));

const BENCHMARKS: BenchmarkHistoryMap = {
  SPY: { current: 101, history: [{ date: '2026-06-17', price: 100 }, { date: '2026-06-18', price: 101 }] },
  QQQ: { current: 203, history: [{ date: '2026-06-17', price: 200 }, { date: '2026-06-18', price: 203 }] },
  DIA: { current: 299, history: [{ date: '2026-06-17', price: 300 }, { date: '2026-06-18', price: 299 }] },
  IWM: { current: 91, history: [{ date: '2026-06-17', price: 90 }, { date: '2026-06-18', price: 91 }] },
};

describe('TopAssetsPulse', () => {
  it('exposes discoverable scroll controls and a keyboard-focusable region', () => {
    const html = renderToStaticMarkup(createElement(TopAssetsPulse, { benchmarks: BENCHMARKS }));

    expect(html).toContain('aria-label="Scroll left (loops to end)"');
    expect(html).toContain('aria-label="Scroll right (loops to start)"');
    expect(html).toContain('title="Scroll market pulse left"');
    expect(html).toContain('role="region"');
    expect(html).toContain('aria-label="Market pulse assets"');
    expect(html).toContain('tabindex="0"');
  });
});
