import { describe, expect, it } from 'vitest';
import {
  barFillPct,
  currencyColor,
  LEAN_BAND,
  SCORE_MAX,
  scoreColorClass,
  scoreLabel,
  STRONG_BAND,
  tickPct,
} from './consensus-bar';

describe('consensus-bar constants', () => {
  it('exposes the canonical band values', () => {
    expect(SCORE_MAX).toBe(2);
    expect(STRONG_BAND).toBe(1.25);
    expect(LEAN_BAND).toBe(0.35);
  });
});

describe('scoreColorClass', () => {
  it('is green at and above the lean band', () => {
    expect(scoreColorClass(LEAN_BAND)).toBe('text-up');
    expect(scoreColorClass(1.5)).toBe('text-up');
  });

  it('is red at and below the negative lean band', () => {
    expect(scoreColorClass(-LEAN_BAND)).toBe('text-down');
    expect(scoreColorClass(-1.5)).toBe('text-down');
  });

  it('is secondary inside the neutral band', () => {
    expect(scoreColorClass(0)).toBe('text-ink-soft');
    expect(scoreColorClass(0.34)).toBe('text-ink-soft');
    expect(scoreColorClass(-0.34)).toBe('text-ink-soft');
  });
});

describe('scoreLabel', () => {
  it('labels strong bands at the boundary', () => {
    expect(scoreLabel(STRONG_BAND)).toBe('Strong bull');
    expect(scoreLabel(-STRONG_BAND)).toBe('Strong bear');
  });

  it('labels lean bands at the boundary', () => {
    expect(scoreLabel(LEAN_BAND)).toBe('Bullish lean');
    expect(scoreLabel(-LEAN_BAND)).toBe('Bearish lean');
  });

  it('labels the neutral interior', () => {
    expect(scoreLabel(0)).toBe('Neutral');
    expect(scoreLabel(0.34)).toBe('Neutral');
    expect(scoreLabel(-0.34)).toBe('Neutral');
  });

  it('keeps lean just below the strong boundary', () => {
    expect(scoreLabel(1.24)).toBe('Bullish lean');
    expect(scoreLabel(-1.24)).toBe('Bearish lean');
  });
});

describe('currencyColor', () => {
  it('returns the stable G10 color', () => {
    expect(currencyColor('USD')).toBe('#3B82F6');
    expect(currencyColor('NOK')).toBe('#14B8A6');
  });

  it('falls back to slate for unknown currencies', () => {
    expect(currencyColor('XXX')).toBe('#94a3b8');
  });
});

describe('barFillPct', () => {
  it('is 0 at a zero score', () => {
    expect(barFillPct(0)).toBe(0);
  });

  it('reaches 50 at the score extremes', () => {
    expect(barFillPct(SCORE_MAX)).toBe(50);
    expect(barFillPct(-SCORE_MAX)).toBe(50);
  });

  it('clamps magnitudes beyond the max', () => {
    expect(barFillPct(5)).toBe(50);
    expect(barFillPct(-5)).toBe(50);
  });

  it('is linear in between', () => {
    expect(barFillPct(1)).toBe(25);
  });
});

describe('tickPct', () => {
  it('centers at 50 for a zero value', () => {
    expect(tickPct(0)).toBe(50);
  });

  it('maps the positive extreme to 100', () => {
    expect(tickPct(2)).toBe(100);
  });

  it('maps the negative extreme to 0', () => {
    expect(tickPct(-2)).toBe(0);
  });

  it('clamps out-of-range values', () => {
    expect(tickPct(5)).toBe(100);
    expect(tickPct(-5)).toBe(0);
  });

  it('is linear in between', () => {
    expect(tickPct(1)).toBe(75);
  });
});
