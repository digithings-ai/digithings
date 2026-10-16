import { describe, expect, it } from 'vitest';
import { dominantVerticalWheel } from './chart-wheel';

describe('dominantVerticalWheel', () => {
  it('steals a vertical wheel and leaves a horizontal wheel on the chart', () => {
    expect(dominantVerticalWheel(0, 40)).toBe(true);
    expect(dominantVerticalWheel(12, -40)).toBe(true);
    expect(dominantVerticalWheel(40, 10)).toBe(false);
    expect(dominantVerticalWheel(20, 20)).toBe(false);
  });
});
