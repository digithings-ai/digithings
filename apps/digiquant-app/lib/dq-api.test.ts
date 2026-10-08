import { describe, expect, it } from 'vitest';
import { isStubEnvelope } from './dq-api';

/** Same rule as digiquant-web lib/official-api.ts isStubPayload. */
describe('isStubEnvelope', () => {
  it('withholds the worker double NAV figures as values', () => {
    expect(isStubEnvelope({ data: { nav_tip: { nav: 99.909 } } })).toBe(true);
    expect(isStubEnvelope({ data: { series: [{ nav: 204.04 }] } })).toBe(true);
    expect(isStubEnvelope({ data: { nav: '204.040' } })).toBe(true);
  });

  it('keeps house figures that merely contain the stub digits', () => {
    expect(isStubEnvelope({ data: { nav_tip: { nav: 99.9091 } } })).toBe(false);
    expect(isStubEnvelope({ data: { nav: 1204.04 } })).toBe(false);
  });

  it('keeps a legacy_estimate label on an older house point', () => {
    expect(isStubEnvelope({ data: { series: [{ nav: 101.2, basis: 'legacy_estimate' }] } })).toBe(false);
  });
});
