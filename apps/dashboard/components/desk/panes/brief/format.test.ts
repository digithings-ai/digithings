import { describe, expect, it } from 'vitest';
import { EM_DASH, formatSignedPct, provenanceBadge } from './format';

describe('brief format', () => {
  it('fails closed to an em dash', () => {
    expect(formatSignedPct(null)).toBe(EM_DASH);
    expect(formatSignedPct(undefined)).toBe(EM_DASH);
    expect(formatSignedPct(Number.NaN)).toBe(EM_DASH);
    expect(formatSignedPct(1.5)).toBe('+1.50%');
  });

  it('never labels a live overlay as finalized accounting', () => {
    expect(provenanceBadge({ active: true, badge: 'finalized accounting' })).toBe('live marks');
    expect(provenanceBadge({ active: false, badge: 'finalized accounting' })).toBe(
      'finalized accounting',
    );
    expect(provenanceBadge(null)).toBe(EM_DASH);
  });
});
