// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

const velaMock = vi.hoisted(() => ({
  instances: [] as Array<{ options: Record<string, unknown> }>,
}));

vi.mock('@luxalgo/vela', () => ({
  Vela: class {
    constructor(_host: unknown, options: Record<string, unknown>) {
      velaMock.instances.push({ options });
    }
    destroy() {}
  },
}));

import { DeskChart } from './DeskChart';

const BARS = [{ t: 1_727_740_800_000, o: 100, h: 104, l: 99, c: 103, v: 10 }];

let container: HTMLDivElement | null = null;
let root: Root | null = null;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  velaMock.instances.length = 0;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
});

describe('DeskChart', () => {
  it('draws no placeholder prices when bars are absent', () => {
    const html = renderToStaticMarkup(createElement(DeskChart, { bars: [], symbol: 'XLK' }));
    expect(html).toContain('data-testid="desk-state-empty"');
    expect(html).toContain('No bars');
    expect(html).not.toContain('610.40');
    expect(html).not.toContain('613.80');
    expect(html).not.toContain('desk-chart-host');
  });

  it('mounts Vela with digiquant up and down colors, not theme dark', async () => {
    act(() => {
      root!.render(createElement(DeskChart, { bars: BARS, symbol: 'XLK', timeframe: '1d' }));
    });
    await vi.waitFor(() => expect(velaMock.instances).toHaveLength(1));
    const { options } = velaMock.instances[0]!;
    expect(options.theme).not.toBe('dark');
    expect(options.upColor).toMatch(/^#3dd6c4$/i);
    expect(options.downColor).toMatch(/^#e5533e$/i);
    const theme = options.theme as { upColor: string; downColor: string };
    expect(theme.upColor).toMatch(/^#3dd6c4$/i);
    expect(theme.downColor).toMatch(/^#e5533e$/i);
    expect(options.live).toBe(false);
  });
});
