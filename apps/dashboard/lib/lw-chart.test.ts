import { describe, expect, it } from 'vitest';
import type { Time } from 'lightweight-charts';
import { themedChartOptions, timeToISO, toLineData } from './lw-chart';
import type { ChartColors } from './chart-colors';

const COLORS: ChartColors = {
  up: '#3DD6C4',
  down: '#E5533E',
  warn: '#E0B341',
  accent: '#3DD6C4',
  axis: '#6B7177',
  inkSoft: '#9AA0A6',
  ink: '#ECEEF0',
  hair: 'rgba(255, 255, 255, 0.09)',
  bg: '#0A0E0C',
  surface: '#121417',
  termBg: '#08090B',
};

describe('toLineData (recharts rows → lightweight-charts points)', () => {
  it('maps {date, value} rows to {time, value}', () => {
    const rows = [
      { date: '2026-01-02', nav: 100 },
      { date: '2026-01-03', nav: 101.5 },
    ];
    expect(toLineData(rows, (r) => r.date, (r) => r.nav)).toEqual([
      { time: '2026-01-02', value: 100 },
      { time: '2026-01-03', value: 101.5 },
    ]);
  });

  it('turns null/NaN values into whitespace points (gaps, not bridges)', () => {
    const rows = [
      { date: '2026-01-02', v: null as number | null },
      { date: '2026-01-03', v: NaN },
      { date: '2026-01-06', v: 3 },
    ];
    expect(toLineData(rows, (r) => r.date, (r) => r.v)).toEqual([
      { time: '2026-01-02' },
      { time: '2026-01-03' },
      { time: '2026-01-06', value: 3 },
    ]);
  });

  it('drops duplicate and empty dates (lightweight-charts needs unique ascending times)', () => {
    const rows = [
      { date: '2026-01-02', v: 1 },
      { date: '2026-01-02', v: 2 },
      { date: '', v: 3 },
      { date: '2026-01-03', v: 4 },
    ];
    expect(toLineData(rows, (r) => r.date, (r) => r.v)).toEqual([
      { time: '2026-01-02', value: 1 },
      { time: '2026-01-03', value: 4 },
    ]);
  });
});

describe('timeToISO', () => {
  it('passes ISO strings through', () => {
    expect(timeToISO('2026-07-08' as Time)).toBe('2026-07-08');
  });
  it('formats BusinessDay objects', () => {
    expect(timeToISO({ year: 2026, month: 7, day: 8 } as Time)).toBe('2026-07-08');
  });
  it('formats UTC-seconds timestamps', () => {
    expect(timeToISO(1767225600 as Time)).toBe('2026-01-01');
  });
});

describe('themedChartOptions (token theme surface)', () => {
  const opts = themedChartOptions(COLORS, 'monospace');

  it('keeps the canvas transparent and brands nothing', () => {
    expect(opts.layout?.background).toMatchObject({ color: 'transparent' });
    expect(opts.layout?.attributionLogo).toBe(false);
  });

  it('derives every chrome color from the token palette', () => {
    expect(opts.layout?.textColor).toBe(COLORS.axis);
    expect(opts.grid?.vertLines?.color).toBe(COLORS.hair);
    expect(opts.grid?.horzLines?.color).toBe(COLORS.hair);
    expect(opts.rightPriceScale?.borderColor).toBe(COLORS.hair);
    expect(opts.leftPriceScale?.borderColor).toBe(COLORS.hair);
    expect(opts.timeScale?.borderColor).toBe(COLORS.hair);
    expect(opts.crosshair?.vertLine?.color).toBe(COLORS.axis);
    expect(opts.crosshair?.vertLine?.labelBackgroundColor).toBe(COLORS.accent);
    expect(opts.crosshair?.horzLine?.labelBackgroundColor).toBe(COLORS.accent);
  });
});
