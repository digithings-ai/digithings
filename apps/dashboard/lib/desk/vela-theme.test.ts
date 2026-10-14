import { describe, expect, it } from 'vitest';
import {
  DIGIQUANT_DOWN,
  DIGIQUANT_UP,
  DIGIQUANT_WARN,
  deskChartWheelAction,
  deskVelaOptions,
} from './vela-theme';

describe('deskVelaOptions', () => {
  it('paints candles digiquant teal and red, not a stock theme name', () => {
    const options = deskVelaOptions(
      [{ t: 1, o: 1, h: 2, l: 0.5, c: 1.5 }],
      '1d',
      { background: '#0A0E0C', text: '#ECEEF0', grid: 'rgba(255, 255, 255, 0.09)' },
    );
    expect(options.upColor).toBe(DIGIQUANT_UP);
    expect(options.downColor).toBe(DIGIQUANT_DOWN);
    expect(options.upColor.toLowerCase()).toBe('#3dd6c4');
    expect(options.downColor.toLowerCase()).toBe('#e5533e');
    expect(DIGIQUANT_WARN.toLowerCase()).toBe('#e0b341');
    expect(options.theme.upColor).toBe(DIGIQUANT_UP);
    expect(options.theme).not.toBe('dark');
    expect(options.live).toBe(false);
    expect(options.theme.fontFamily.toLowerCase()).not.toContain('inter');
  });
});

describe('deskChartWheelAction', () => {
  it('scrolls the pane on a vertical wheel and leaves a horizontal wheel to the chart', () => {
    expect(deskChartWheelAction({ deltaX: 0, deltaY: 40 })).toBe('scroll-pane');
    expect(deskChartWheelAction({ deltaX: 40, deltaY: 2 })).toBe('chart');
    expect(deskChartWheelAction({ deltaX: 10, deltaY: 10 })).toBe('chart');
  });
});
