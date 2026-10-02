// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DIGIQUANT_DOWN, DIGIQUANT_UP } from '@/lib/desk/vela-theme';

const velaMock = vi.hoisted(() => ({
  instances: [] as Array<{ host: unknown; options: Record<string, unknown> }>,
}));

vi.mock('@luxalgo/vela', () => ({
  Vela: class {
    constructor(host: unknown, options: Record<string, unknown>) {
      velaMock.instances.push({ host, options });
    }
    destroy() {}
  },
}));

import { DeskChart } from './DeskChart';

const BARS = [{ t: 1727740800000, o: 10, h: 12, l: 9, c: 11, v: 4 }];

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

function renderInScroller(): HTMLElement {
  const scroller = document.createElement('div');
  scroller.setAttribute('data-desk-pane-scroll', '');
  const host = document.createElement('div');
  scroller.appendChild(host);
  container!.appendChild(scroller);
  act(() => root!.unmount());
  root = createRoot(host);
  return scroller;
}

describe('DeskChart', () => {
  it('constructs Vela with DigiQuant candle colors', async () => {
    act(() => {
      root!.render(createElement(DeskChart, { bars: BARS, timeframe: '1d' }));
    });
    await vi.waitFor(() => expect(velaMock.instances).toHaveLength(1));
    const [{ options }] = velaMock.instances;
    expect(options.upColor).toBe(DIGIQUANT_UP);
    expect(options.downColor).toBe(DIGIQUANT_DOWN);
    expect(options.theme).not.toBe('dark');
    expect(options.live).toBe(false);
    expect((options.theme as { upColor: string }).upColor).toBe(DIGIQUANT_UP);
  });

  it('scrolls the pane on a vertical wheel and does not steal a horizontal wheel', async () => {
    const scroller = renderInScroller();
    act(() => {
      root!.render(createElement(DeskChart, { bars: BARS }));
    });
    await vi.waitFor(() => expect(velaMock.instances).toHaveLength(1));

    const host = scroller.querySelector('[data-testid="desk-chart-host"]');
    expect(host).toBeTruthy();
    scroller.scrollTop = 0;

    const vertical = new WheelEvent('wheel', { deltaX: 0, deltaY: 36, bubbles: true, cancelable: true });
    host!.dispatchEvent(vertical);
    expect(vertical.defaultPrevented).toBe(true);
    expect(scroller.scrollTop).toBe(36);

    const before = scroller.scrollTop;
    const horizontal = new WheelEvent('wheel', { deltaX: 48, deltaY: 1, bubbles: true, cancelable: true });
    host!.dispatchEvent(horizontal);
    expect(horizontal.defaultPrevented).toBe(false);
    expect(scroller.scrollTop).toBe(before);
  });
});
