import { describe, expect, it } from 'vitest';
import {
  consensusScoreBarProps,
  LEAN_BAND,
  SCORE_MAX,
  scoreColorClass,
  scoreLabel,
  STRONG_BAND,
} from './consensus-bar';

describe('consensus-bar constants', () => {
  it('exposes the canonical band values', () => {
    expect(SCORE_MAX).toBe(2);
    expect(STRONG_BAND).toBe(1.25);
    expect(LEAN_BAND).toBe(0.35);
  });
});

describe('scoreColorClass', () => {
  it('is accent at and above the lean band', () => {
    expect(scoreColorClass(LEAN_BAND)).toBe('text-accent');
    expect(scoreColorClass(1.5)).toBe('text-accent');
  });

  it('is warn at and below the negative lean band', () => {
    expect(scoreColorClass(-LEAN_BAND)).toBe('text-warn');
    expect(scoreColorClass(-1.5)).toBe('text-warn');
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

describe('consensusScoreBarProps', () => {
  it('uses the symmetric consensus axis', () => {
    const p = consensusScoreBarProps(1);
    expect(p.min).toBe(-SCORE_MAX);
    expect(p.max).toBe(SCORE_MAX);
    expect(p.value).toBe(1);
  });

  it('is accent for bullish and warn for bearish, never up/down', () => {
    expect(consensusScoreBarProps(0.5).tone).toBe('accent');
    expect(consensusScoreBarProps(0).tone).toBe('accent');
    expect(consensusScoreBarProps(-0.5).tone).toBe('warn');
  });

  it('draws the empty track for non-finite values', () => {
    expect(consensusScoreBarProps(null).value).toBeNull();
    expect(consensusScoreBarProps(Number.NaN).value).toBeNull();
    expect(consensusScoreBarProps(undefined).tone).toBe('accent');
  });

  it('adds one labelled reference tick only when an actual is given', () => {
    expect(consensusScoreBarProps(1).ticks).toEqual([]);
    const p = consensusScoreBarProps(1, { value: 1.4, label: "Today's actual" });
    expect(p.ticks).toEqual([{ value: 1.4, label: "Today's actual", tone: 'ink' }]);
  });

  it('formats signed to two decimals', () => {
    const p = consensusScoreBarProps(1);
    expect(p.format(0.5)).toBe('+0.50');
    expect(p.format(-1.234)).toBe('-1.23');
  });
});
