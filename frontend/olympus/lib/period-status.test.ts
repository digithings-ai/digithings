import { describe, expect, it } from 'vitest';
import { periodStatusLabel } from './period-status';

describe('periodStatusLabel', () => {
  it('maps known tip statuses to readable labels', () => {
    expect(periodStatusLabel('final')).toBe('Final');
    expect(periodStatusLabel('estimated')).toBe('Estimated');
    expect(periodStatusLabel('incomplete')).toBe('Incomplete');
    expect(periodStatusLabel('failed')).toBe('Failed');
  });

  it('passes through unknown statuses honestly', () => {
    expect(periodStatusLabel('weird')).toBe('weird');
  });
});
