import { describe, expect, it } from 'vitest';
import { periodStatusLabel } from './period-status';

describe('periodStatusLabel (#2652)', () => {
  it('maps tip statuses without inventing final for incomplete', () => {
    expect(periodStatusLabel('final')).toBe('Final');
    expect(periodStatusLabel('estimated')).toBe('Estimated');
    expect(periodStatusLabel('incomplete')).toBe('Incomplete');
    expect(periodStatusLabel('failed')).toBe('Failed');
    expect(periodStatusLabel('weird')).toBe('weird');
  });
});
