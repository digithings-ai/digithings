// @vitest-environment happy-dom
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const navMock = vi.hoisted(() => ({ params: '' }));

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(navMock.params),
}));

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

import VelaSpikePage from './page';

function barsPayload(symbol: string, timeframe: string) {
  return {
    symbol,
    timeframe,
    limit: 120,
    count: 1,
    bars: [{ timestamp: '2024-10-01', open: 100, high: 104, low: 99, close: 103, volume: 5 }],
    source: 'gloomberb',
    stale: false,
    delay_note: 'Free-tier data delayed up to 15 minutes',
  };
}

let container: HTMLDivElement | null = null;
let root: Root | null = null;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  velaMock.instances.length = 0;
  navMock.params = '';
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  vi.unstubAllGlobals();
});

function text() {
  return container!.textContent ?? '';
}

describe('app/research/vela-spike/page', () => {
  it('shows loading, then wires fetched bars into the chart with route params', async () => {
    navMock.params = 'symbol=ETH-USD&timeframe=1h';
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify(barsPayload('ETH-USD', '1h')), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    act(() => {
      root!.render(createElement(VelaSpikePage));
    });
    expect(container!.querySelector('[data-testid="vela-spike-loading"]')).not.toBeNull();

    await vi.waitFor(() => expect(velaMock.instances).toHaveLength(1));

    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toContain('/bars?');
    expect(url).toContain('symbol=ETH-USD');
    expect(url).toContain('timeframe=1h');
    expect(text()).toContain('ETH-USD');
    expect(text()).toContain('Sourced from Gloomberb');
    expect(text()).toContain('Free-tier data delayed up to 15 minutes');
    const [{ options }] = velaMock.instances;
    expect(options.timeframe).toBe('1h');
    expect(options.live).toBe(false);
  });

  it('defaults to the crypto symbol and daily timeframe with no params', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify(barsPayload('BTC-USD', '1d')), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    act(() => {
      root!.render(createElement(VelaSpikePage));
    });
    await vi.waitFor(() => expect(velaMock.instances).toHaveLength(1));

    const [url] = fetchMock.mock.calls[0] as unknown as [string];
    expect(url).toContain('symbol=BTC-USD');
    expect(url).toContain('timeframe=1d');
  });

  it('renders an error state with retry when the read fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ detail: 'nope' }), { status: 500 }))
    );

    act(() => {
      root!.render(createElement(VelaSpikePage));
    });
    await vi.waitFor(() =>
      expect(container!.querySelector('[data-testid="vela-spike-error"]')).not.toBeNull()
    );
    expect(text()).toContain('nope');
    expect(velaMock.instances).toHaveLength(0);
  });
});
