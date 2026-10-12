import { describe, expect, it } from 'vitest';
import { isStubEnvelope } from './stub-envelope';

describe('isStubEnvelope', () => {
  it('flags the secretless NAV doubles and leaves a real book', () => {
    expect(isStubEnvelope({ data: { nav_tip: { nav: 204.04, contract: 'finalized_accounting' } } })).toBe(true);
    expect(isStubEnvelope({ data: { nav_tip: { nav: 99.909, contract: 'legacy_estimate' } } })).toBe(true);
    expect(isStubEnvelope({ data: { since_inception_live_pct: 104.44808 } })).toBe(true);
    expect(
      isStubEnvelope({
        data: { nav_tip: { nav: 112.4, contract: 'finalized_accounting' }, since_inception_pct: 1.25 },
      }),
    ).toBe(false);
  });
});
