import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import VelaSpikeChart, {
  VELA_PROJECT_URL,
  VELA_VERSION,
  type VelaSpikeBar,
} from './VelaSpikeChart';

const BARS: VelaSpikeBar[] = [
  { t: 1727740800000, o: 100, h: 104, l: 99, c: 103, v: 1200 },
  { t: 1727827200000, o: 103, h: 107, l: 102, c: 106, v: 1500 },
  { t: 1727913600000, o: 106, h: 108, l: 104, c: 105, v: 900 },
];

describe('VelaSpikeChart', () => {
  it('renders the symbol caption with bar count and range plus the experimental badge', () => {
    const html = renderToStaticMarkup(
      createElement(VelaSpikeChart, { bars: BARS, symbol: 'BTCUSDT', timeframe: '1D' })
    );
    expect(html).toContain('data-testid="vela-spike-chart"');
    expect(html).toContain('BTCUSDT');
    expect(html).toContain('3 bars');
    expect(html).toContain('experimental');
    expect(html).toContain('data-testid="vela-spike-host"');
  });

  it('shows visible Vela attribution on the same screen (NOTICE requirement)', () => {
    const html = renderToStaticMarkup(
      createElement(VelaSpikeChart, { bars: BARS, symbol: 'BTCUSDT' })
    );
    expect(html).toContain('data-testid="vela-attribution"');
    expect(html).toContain('Vela (LuxAlgo)');
    expect(html).toContain(`href="${VELA_PROJECT_URL}"`);
    expect(html).toContain('Open in QuantCharts');
    expect(VELA_VERSION).toBe('0.8.0');
  });

  it('makes no network calls when rendering from offline bars', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('no network'));
    try {
      renderToStaticMarkup(createElement(VelaSpikeChart, { bars: BARS, symbol: 'BTCUSDT' }));
      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it('renders an empty state with no bars', () => {
    const html = renderToStaticMarkup(createElement(VelaSpikeChart, { bars: [], symbol: 'BTCUSDT' }));
    expect(html).toContain('No bars for BTCUSDT yet.');
  });
});
