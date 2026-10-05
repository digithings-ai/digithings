// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const velaMock = vi.hoisted(() => ({
  instances: [] as Array<{ host: unknown; options: Record<string, unknown> }>,
  destroyed: 0,
}));

vi.mock('@luxalgo/vela', () => ({
  Vela: class {
    constructor(host: unknown, options: Record<string, unknown>) {
      velaMock.instances.push({ host, options });
    }
    destroy() {
      velaMock.destroyed += 1;
    }
  },
}));

import VelaSpikeChart, { type VelaSpikeBar } from './VelaSpikeChart';
import { barsResponseToVelaBars } from '@/lib/vela-bars';

const BARS: VelaSpikeBar[] = [
  { t: 1727740800000, o: 100, h: 104, l: 99, c: 103, v: 1200 },
  { t: 1727827200000, o: 103, h: 107, l: 102, c: 106 },
];

let container: HTMLDivElement | null = null;
let root: Root | null = null;
let fetchSpy: ReturnType<typeof vi.spyOn> | null = null;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  velaMock.instances.length = 0;
  velaMock.destroyed = 0;
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('no network'));
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  fetchSpy?.mockRestore();
  fetchSpy = null;
});

async function renderAndWaitForMount() {
  // Render inside act; the mocked dynamic import resolves on the event loop,
  // so poll for the constructor call outside act (vi.waitFor inside act stalls).
  act(() => {
    root!.render(createElement(VelaSpikeChart, { bars: BARS, symbol: 'BTCUSDT' }));
  });
  await vi.waitFor(() => expect(velaMock.instances).toHaveLength(1));
}

describe('VelaSpikeChart mount (happy-dom, @luxalgo/vela mocked)', () => {
  it('constructs Vela read-only: live:false, offline data shape, no provider, no network', async () => {
    await renderAndWaitForMount();

    const [{ host, options }] = velaMock.instances;
    expect(host).toBe(container!.querySelector('[data-testid="vela-spike-host"]'));
    // Read-only: static history, no live forming candle, drawings toolbar hidden.
    expect(options.live).toBe(false);
    expect(options.drawings).toBe(false);
    expect(options.timeframe).toBe('1D');
    // Offline bars map 1:1 onto Vela's OHLCV option (volume omitted when absent).
    expect(options.data).toEqual([
      { time: 1727740800000, open: 100, high: 104, low: 99, close: 103, volume: 1200 },
      { time: 1727827200000, open: 103, high: 107, low: 102, close: 106 },
    ]);
    // No provider path: with offline `data` set, Vela makes no network fetch.
    expect(options).not.toHaveProperty('provider');
    expect(options).not.toHaveProperty('symbol');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('destroys the chart on unmount', async () => {
    await renderAndWaitForMount();
    act(() => root!.unmount());
    expect(velaMock.destroyed).toBe(1);
  });

  it('data path: BarsResponse-shaped crypto payload maps onto offline constructor args', async () => {
    // #4879 data path — the page fetches keyless GET /bars and maps each
    // BarsBar through barsResponseToVelaBars; the constructor must see the
    // mapped offline `data` shape with the normalized (lowercase) timeframe.
    const payload = {
      symbol: 'BTC-USD',
      timeframe: '1d',
      limit: 120,
      count: 2,
      bars: [
        { timestamp: '2024-10-01', open: 100, high: 104, low: 99, close: 103, volume: 1200 },
        { timestamp: '2024-10-02', open: 103, high: 107, low: 102, close: 106, volume: null },
      ],
      source: 'gloomberb',
      stale: false,
      delay_note: null,
    };
    const mapped = barsResponseToVelaBars(payload);
    expect(mapped).toHaveLength(2);

    act(() => {
      root!.render(createElement(VelaSpikeChart, { bars: mapped, symbol: 'BTC-USD', timeframe: '1d' }));
    });
    await vi.waitFor(() => expect(velaMock.instances).toHaveLength(1));

    const [{ options }] = velaMock.instances;
    expect(options.timeframe).toBe('1d');
    expect(options.live).toBe(false);
    expect(options).not.toHaveProperty('provider');
    expect(options.data).toEqual([
      { time: Date.parse('2024-10-01'), open: 100, high: 104, low: 99, close: 103, volume: 1200 },
      { time: Date.parse('2024-10-02'), open: 103, high: 107, low: 102, close: 106 },
    ]);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
